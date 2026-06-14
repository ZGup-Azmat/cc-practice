#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄钟 Pomodoro Timer — 时间记录 + 数据看板
Python Flask 后端 + SQLite + 系统托盘
"""

import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import datetime
import threading
import webbrowser
import zipfile
from pathlib import Path

from flask import Flask, request, jsonify, g

# ── 配置 ──────────────────────────────────────────────────
# PyInstaller 打包后 __file__ 指向临时目录(关闭即清空)，
# 必须用 sys.executable 来定位 .exe 所在目录，保证数据持久化
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / 'pomodoro.db'
HOST = '127.0.0.1'
PORT = 5678

app = Flask(__name__, static_folder='static', static_url_path='')

# ── 数据库 ────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pomodoro_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT    NOT NULL,
            start_time      TEXT    NOT NULL,
            duration_minutes INTEGER NOT NULL,
            status          TEXT    NOT NULL CHECK(status IN ('completed','abandoned')),
            tag             TEXT    DEFAULT '',
            focus_score     INTEGER DEFAULT NULL,
            reflection      TEXT    DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_date ON pomodoro_records(date);
        CREATE INDEX IF NOT EXISTS idx_tag  ON pomodoro_records(tag);
        CREATE TABLE IF NOT EXISTS tags (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL UNIQUE,
            color      TEXT    DEFAULT '#27AE60',
            icon       TEXT    DEFAULT '',
            created_at TEXT    NOT NULL
        );
    """)
    # v3.1: 加列（如果旧表没有）
    cols = {row[1] for row in db.execute("PRAGMA table_info(tags)")}
    if 'target_pomodoros' not in cols:
        db.execute("ALTER TABLE tags ADD COLUMN target_pomodoros INTEGER DEFAULT NULL")
    if 'tag_type' not in cols:
        db.execute("ALTER TABLE tags ADD COLUMN tag_type TEXT DEFAULT 'daily'")
    # 仅在 tags 表为空时迁移历史 tag 名（避免复活已删除标签）
    existing_count = db.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    if existing_count == 0:
        db.execute("""
            INSERT OR IGNORE INTO tags (name, color, icon, created_at)
            SELECT DISTINCT tag, '#27AE60', '', datetime('now')
            FROM pomodoro_records WHERE tag != ''
        """)
    defaults = {
        'work_duration':          '25',
        'short_break_duration':   '5',
        'long_break_duration':    '15',
        'pomodoros_before_long':  '4',
        'daily_goal_minutes':     '120',
        'theme':                  'light',
        'last_tag':               '',
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    db.commit()
    db.close()

# ── 辅助函数 ──────────────────────────────────────────────

def load_settings(db):
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {row['key']: row['value'] for row in rows}

def _validate_tag_name(name):
    """验证标签名，返回 (valid, error_message)"""
    if not name or len(name) > 12:
        return False, '标签名需 1-12 个字符'
    return True, ''

def _get_tag_colors(db):
    """返回 {tag_name: {color, icon}} 映射，用于附加标签样式"""
    rows = db.execute("SELECT name, color, icon FROM tags").fetchall()
    return {r['name']: r for r in rows}

GHOST_COLOR = '#94A3B8'   # 已删除标签的 fallback 灰色
VALID_TAG_TYPES = {'daily', 'once', 'long'}

def _parse_target_pomodoros(value):
    """解析目标番茄数，非法/超出范围返回 None"""
    if value is None:
        return None
    try:
        n = int(value)
        return n if 1 <= n <= 20 else None
    except (ValueError, TypeError):
        return None

# 自动初始化（首次请求时检查） ──────────────────────────────
_db_initialized = False

@app.before_request
def ensure_db():
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True

# ── 路由 ──────────────────────────────────────────────────

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/mini')
def mini():
    return app.send_static_file('mini.html')

# 计时器状态（供迷你窗轮询）
_TIMER_STATE_KEYS = ('isRunning', 'timeLeft', 'totalTime', 'mode', 'selectedTag')
_timer_state = {
    'isRunning': False,
    'timeLeft': 25 * 60,
    'totalTime': 25 * 60,
    'mode': 'work',
    'selectedTag': '',
}

@app.route('/api/timer-state', methods=['GET'])
def api_get_timer_state():
    return jsonify(_timer_state)

@app.route('/api/timer-state', methods=['PUT'])
def api_update_timer_state():
    data = request.get_json() or {}
    for k in _TIMER_STATE_KEYS:
        if k in data:
            _timer_state[k] = data[k]
    return jsonify({'ok': True})

# --- 设置 API ---

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    db = get_db()
    settings = load_settings(db)
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
def api_update_settings():
    db = get_db()
    data = request.get_json()
    allowed = {
        'work_duration', 'short_break_duration', 'long_break_duration',
        'pomodoros_before_long', 'daily_goal_minutes', 'theme', 'last_tag'
    }
    for key, value in data.items():
        if key in allowed:
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                       (key, str(value)))
    db.commit()
    return jsonify({'ok': True})

# --- 记录 API ---

@app.route('/api/records', methods=['GET'])
def api_get_records():
    db = get_db()
    date_from = request.args.get('from')
    date_to   = request.args.get('to')
    tag       = request.args.get('tag')
    limit     = request.args.get('limit', 100, type=int)

    sql  = "SELECT * FROM pomodoro_records WHERE 1=1"
    params = []
    if date_from:
        sql += " AND date >= ?"; params.append(date_from)
    if date_to:
        sql += " AND date <= ?"; params.append(date_to)
    if tag:
        sql += " AND tag = ?"; params.append(tag)
    sql += " ORDER BY start_time DESC LIMIT ?"; params.append(limit)

    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/records', methods=['POST'])
def api_create_record():
    db = get_db()
    data = request.get_json()
    now = datetime.datetime.now().isoformat()

    db.execute("""
        INSERT INTO pomodoro_records (date, start_time, duration_minutes, status, tag, focus_score, reflection)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('date', datetime.date.today().isoformat()),
        data.get('start_time', now),
        data.get('duration_minutes', 0),
        data.get('status', 'completed'),
        data.get('tag', ''),
        data.get('focus_score'),
        data.get('reflection', ''),
    ))
    db.commit()
    record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({'id': record_id, 'ok': True})

# --- 统计 API ---

@app.route('/api/stats/today', methods=['GET'])
def api_stats_today():
    db = get_db()
    today = datetime.date.today().isoformat()
    rows = db.execute("""
        SELECT COALESCE(SUM(duration_minutes), 0) AS total_minutes,
               COUNT(*) AS count
        FROM pomodoro_records
        WHERE date = ? AND status = 'completed'
    """, (today,)).fetchone()
    goal = db.execute("SELECT value FROM settings WHERE key='daily_goal_minutes'").fetchone()
    goal_minutes = int(goal['value']) if goal else 120
    return jsonify({
        'date': today,
        'total_minutes': rows['total_minutes'],
        'pomodoro_count': rows['count'],
        'goal_minutes': goal_minutes,
        'goal_percent': round(rows['total_minutes'] / goal_minutes * 100, 1) if goal_minutes > 0 else 0,
    })

@app.route('/api/stats/summary', methods=['GET'])
def api_stats_summary():
    db = get_db()
    today = datetime.date.today()
    # 今日
    today_row = db.execute("""
        SELECT COALESCE(SUM(duration_minutes),0) AS m, COUNT(*) AS c
        FROM pomodoro_records WHERE date=? AND status='completed'
    """, (today.isoformat(),)).fetchone()

    # 本周 (周一 ~ 周日)
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end   = week_start + datetime.timedelta(days=6)
    week_row = db.execute("""
        SELECT COALESCE(SUM(duration_minutes),0) AS m, COUNT(*) AS c
        FROM pomodoro_records
        WHERE date BETWEEN ? AND ? AND status='completed'
    """, (week_start.isoformat(), week_end.isoformat())).fetchone()
    week_days = (today - week_start).days + 1

    # 本月
    month_start = today.replace(day=1)
    month_row = db.execute("""
        SELECT COALESCE(SUM(duration_minutes),0) AS m, COUNT(*) AS c
        FROM pomodoro_records
        WHERE date BETWEEN ? AND ? AND status='completed'
    """, (month_start.isoformat(), today.isoformat())).fetchone()
    month_days = today.day

    # 连续天数 streak：从今天往回数，今天无记录则从昨天开始
    streak = 0
    cur = today
    while True:
        row = db.execute("""
            SELECT COUNT(*) AS c FROM pomodoro_records
            WHERE date=? AND status='completed'
        """, (cur.isoformat(),)).fetchone()
        if row['c'] > 0:
            streak += 1
            cur -= datetime.timedelta(days=1)
        elif streak == 0 and cur == today:
            cur -= datetime.timedelta(days=1)  # 今天无记录，从昨天继续
        else:
            break

    # 累计总时长
    total_row = db.execute("""
        SELECT COALESCE(SUM(duration_minutes),0) AS m FROM pomodoro_records WHERE status='completed'
    """).fetchone()

    # Top 3 标签
    tag_rows = db.execute("""
        SELECT tag, COUNT(*) AS c, SUM(duration_minutes) AS m
        FROM pomodoro_records WHERE status='completed' AND tag != ''
        GROUP BY tag ORDER BY c DESC LIMIT 3
    """).fetchall()

    goal = db.execute("SELECT value FROM settings WHERE key='daily_goal_minutes'").fetchone()
    goal_minutes = int(goal['value']) if goal else 120

    return jsonify({
        'today': {
            'total_minutes': today_row['m'],
            'pomodoro_count': today_row['c'],
            'goal_minutes': goal_minutes,
            'goal_percent': round(today_row['m'] / goal_minutes * 100, 1) if goal_minutes > 0 else 0,
        },
        'week': {
            'total_minutes': week_row['m'],
            'avg_daily': round(week_row['m'] / max(week_days, 1), 1),
            'pomodoro_count': week_row['c'],
        },
        'month': {
            'total_minutes': month_row['m'],
            'avg_daily': round(month_row['m'] / max(month_days, 1), 1),
            'pomodoro_count': month_row['c'],
        },
        'streak': streak,
        'total_all_time': total_row['m'],
        'top_tags': [{'tag': r['tag'], 'count': r['c'], 'minutes': r['m']} for r in tag_rows],
    })

# --- 按标签统计 API ---

@app.route('/api/stats/by-tag', methods=['GET'])
def api_stats_by_tag():
    db = get_db()
    period = request.args.get('period', 'all')  # 'all' | 'week' | 'month' | 'today'

    sql = """
        SELECT tag, COUNT(*) AS cnt, SUM(duration_minutes) AS total_min
        FROM pomodoro_records
        WHERE status='completed' AND tag != ''
    """
    params = []

    today = datetime.date.today()
    if period == 'today':
        sql += " AND date = ?"
        params.append(today.isoformat())
    elif period == 'week':
        week_start = today - datetime.timedelta(days=today.weekday())
        sql += " AND date >= ?"
        params.append(week_start.isoformat())
    elif period == 'month':
        sql += " AND date >= ?"
        params.append(today.replace(day=1).isoformat())

    sql += " GROUP BY tag ORDER BY total_min DESC"

    rows = db.execute(sql, params).fetchall()
    tag_colors = _get_tag_colors(db)
    result = []
    for r in rows:
        tinfo = tag_colors.get(r['tag'])
        result.append({
            'tag': r['tag'],
            'count': r['cnt'],
            'total_minutes': r['total_min'],
            'color': tinfo['color'] if tinfo else GHOST_COLOR,
            'icon': tinfo['icon'] if tinfo else '',
        })

    # 总计（含无标签记录）
    total_sql = """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(duration_minutes), 0) AS total_min
        FROM pomodoro_records WHERE status='completed'
    """
    total_params = []
    if period == 'today':
        total_sql += " AND date = ?"
        total_params.append(today.isoformat())
    elif period == 'week':
        total_sql += " AND date >= ?"
        total_params.append((today - datetime.timedelta(days=today.weekday())).isoformat())
    elif period == 'month':
        total_sql += " AND date >= ?"
        total_params.append(today.replace(day=1).isoformat())

    total_row = db.execute(total_sql, total_params).fetchone()

    return jsonify({
        'tags': result,
        'total_pomodoros': total_row['cnt'],
        'total_minutes': total_row['total_min'],
    })

# --- 标签管理 API ---

@app.route('/api/tags', methods=['GET'])
def api_get_tags():
    db = get_db()
    rows = db.execute("SELECT * FROM tags ORDER BY created_at").fetchall()
    today = datetime.date.today().isoformat()
    # 每个标签今日完成数
    today_counts = {}
    for r in db.execute("""
        SELECT tag, COUNT(*) AS cnt FROM pomodoro_records
        WHERE date = ? AND status = 'completed' AND tag != ''
        GROUP BY tag
    """, (today,)).fetchall():
        today_counts[r['tag']] = r['cnt']
    # 每个标签全部完成数（仅一次性标签需要）
    all_counts = {}
    for r in db.execute("""
        SELECT tag, COUNT(*) AS cnt FROM pomodoro_records
        WHERE status = 'completed' AND tag != ''
        GROUP BY tag
    """).fetchall():
        all_counts[r['tag']] = r['cnt']
    result = []
    for r in rows:
        d = dict(r)
        d['today_done'] = today_counts.get(r['name'], 0)
        d['all_done'] = all_counts.get(r['name'], 0)
        result.append(d)
    return jsonify(result)

@app.route('/api/tags', methods=['POST'])
def api_create_tag():
    db = get_db()
    data = request.get_json()
    name = (data.get('name') or '').strip()
    ok, err = _validate_tag_name(name)
    if not ok:
        return jsonify({'ok': False, 'error': err}), 400
    # 检查重名
    existing = db.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if existing:
        return jsonify({'ok': False, 'error': '标签名已存在'}), 400
    color = data.get('color', '#27AE60')
    icon = data.get('icon', '')
    target = _parse_target_pomodoros(data.get('target_pomodoros'))
    tag_type = data.get('tag_type', 'daily')
    if tag_type not in VALID_TAG_TYPES:
        tag_type = 'daily'
    now = datetime.datetime.now().isoformat()
    db.execute(
        "INSERT INTO tags (name, color, icon, target_pomodoros, tag_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, color, icon, target, tag_type, now)
    )
    db.commit()
    tag_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({'ok': True, 'id': tag_id})

@app.route('/api/tags/<int:tag_id>', methods=['PUT'])
def api_update_tag(tag_id):
    db = get_db()
    tag = db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not tag:
        return jsonify({'ok': False, 'error': '标签不存在'}), 404
    data = request.get_json()
    name = (data.get('name') or '').strip()
    ok, err = _validate_tag_name(name)
    if not ok:
        return jsonify({'ok': False, 'error': err}), 400
    # 检查重名（排除自身）
    existing = db.execute("SELECT id FROM tags WHERE name = ? AND id != ?", (name, tag_id)).fetchone()
    if existing:
        return jsonify({'ok': False, 'error': '标签名已存在'}), 400
    color = data.get('color', tag['color'])
    icon = data.get('icon', tag['icon'])
    target = _parse_target_pomodoros(data.get('target_pomodoros', tag['target_pomodoros']))
    tag_type = data.get('tag_type', tag['tag_type'] or 'daily')
    if tag_type not in VALID_TAG_TYPES:
        tag_type = 'daily'
    db.execute(
        "UPDATE tags SET name = ?, color = ?, icon = ?, target_pomodoros = ?, tag_type = ? WHERE id = ?",
        (name, color, icon, target, tag_type, tag_id)
    )
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    db = get_db()
    tag = db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not tag:
        return jsonify({'ok': False, 'error': '标签不存在'}), 404
    # 只删 tags 表，不动 pomodoro_records
    db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/tags/progress', methods=['GET'])
def api_tags_progress():
    """返回每个标签今日已完成番茄数"""
    db = get_db()
    today = datetime.date.today().isoformat()
    rows = db.execute("""
        SELECT tag, COUNT(*) AS cnt FROM pomodoro_records
        WHERE date = ? AND status = 'completed' AND tag != ''
        GROUP BY tag
    """, (today,)).fetchall()
    progress = {r['tag']: r['cnt'] for r in rows}
    return jsonify({'progress': progress, 'date': today})

# --- 单日按标签聚合（含已删除标签 fallback） ---

@app.route('/api/stats/day-detail', methods=['GET'])
def api_stats_day_detail():
    db = get_db()
    date = request.args.get('date', datetime.date.today().isoformat())

    # 当日按 tag 聚合
    rows = db.execute("""
        SELECT tag, COUNT(*) AS cnt, SUM(duration_minutes) AS total_min
        FROM pomodoro_records
        WHERE date = ? AND status = 'completed' AND tag != ''
        GROUP BY tag ORDER BY total_min DESC
    """, (date,)).fetchall()

    # 总数
    total_row = db.execute("""
        SELECT COALESCE(SUM(duration_minutes), 0) AS total_min,
               COUNT(*) AS cnt
        FROM pomodoro_records
        WHERE date = ? AND status = 'completed'
    """, (date,)).fetchone()

    # 所有已知标签（用于匹配颜色）
    tag_colors = _get_tag_colors(db)

    details = []
    for r in rows:
        tag_name = r['tag']
        tinfo = tag_colors.get(tag_name)
        details.append({
            'tag': tag_name,
            'count': r['cnt'],
            'total_minutes': r['total_min'],
            'color': tinfo['color'] if tinfo else GHOST_COLOR,
            'icon': tinfo['icon'] if tinfo else '',
        })

    return jsonify({
        'date': date,
        'total_minutes': total_row['total_min'],
        'total_count': total_row['cnt'],
        'details': details,
    })

# --- 热力图数据 ---

@app.route('/api/stats/heatmap', methods=['GET'])
def api_stats_heatmap():
    db = get_db()
    view = request.args.get('view', 'year')   # 'year' | 'month'
    year = request.args.get('year', datetime.date.today().year, type=int)
    month = request.args.get('month', type=int)
    tag  = request.args.get('tag')

    if view == 'month':
        if month is None:
            month = datetime.date.today().month
        from_date = datetime.date(year, month, 1)
        if month == 12:
            to_date = datetime.date(year + 1, 1, 1)
        else:
            to_date = datetime.date(year, month + 1, 1)
    else:
        from_date = datetime.date(year, 1, 1)
        to_date   = datetime.date(year + 1, 1, 1)

    sql = """
        SELECT date, SUM(duration_minutes) AS m, COUNT(*) AS c
        FROM pomodoro_records
        WHERE date >= ? AND date < ? AND status='completed'
    """
    params = [from_date.isoformat(), to_date.isoformat()]
    if tag:
        sql += " AND tag = ?"
        params.append(tag)
    sql += " GROUP BY date ORDER BY date"

    rows = db.execute(sql, params).fetchall()
    data = {r['date']: {'minutes': r['m'], 'count': r['c']} for r in rows}

    # 所有可用标签
    tags = db.execute("""
        SELECT DISTINCT tag FROM pomodoro_records
        WHERE status='completed' AND tag != '' ORDER BY tag
    """).fetchall()

    return jsonify({
        'data': data,
        'from': from_date.isoformat(),
        'to': to_date.isoformat(),
        'tags': [t['tag'] for t in tags],
    })

# --- 趋势数据 ---

@app.route('/api/stats/trend', methods=['GET'])
def api_stats_trend():
    db = get_db()
    granularity = request.args.get('granularity', 'day')  # 'day' | 'week' | 'month'
    days        = request.args.get('days', 90, type=int)
    tag         = request.args.get('tag')
    goal_minutes = int(load_settings(db).get('daily_goal_minutes', 120))

    to_date = datetime.date.today()
    from_date = to_date - datetime.timedelta(days=days)

    if granularity == 'day':
        sql = """
            SELECT date, SUM(duration_minutes) AS m, COUNT(*) AS c
            FROM pomodoro_records
            WHERE date BETWEEN ? AND ? AND status='completed'
        """
        params = [from_date.isoformat(), to_date.isoformat()]
        if tag:
            sql += " AND tag = ?"
            params.append(tag)
        sql += " GROUP BY date ORDER BY date"

        rows = db.execute(sql, params).fetchall()
        # 填充所有日期（包括无记录的）
        data_map = {r['date']: {'minutes': r['m'], 'count': r['c']} for r in rows}
        result = []
        cur = from_date
        while cur <= to_date:
            iso = cur.isoformat()
            entry = data_map.get(iso, {'minutes': 0, 'count': 0})
            result.append({'date': iso, **entry})
            cur += datetime.timedelta(days=1)

        return jsonify({'data': result, 'goal_minutes': goal_minutes})

    elif granularity == 'week':
        sql = """
            SELECT strftime('%Y-W%W', date) AS week, SUM(duration_minutes) AS m, COUNT(*) AS c
            FROM pomodoro_records
            WHERE date BETWEEN ? AND ? AND status='completed'
        """
        params = [from_date.isoformat(), to_date.isoformat()]
        if tag:
            sql += " AND tag = ?"
            params.append(tag)
        sql += " GROUP BY week ORDER BY week"
        rows = db.execute(sql, params).fetchall()
        return jsonify({
            'data': [{'period': r['week'], 'minutes': r['m'], 'count': r['c']} for r in rows],
            'goal_minutes': goal_minutes * 7,
        })

    elif granularity == 'month':
        sql = """
            SELECT strftime('%Y-%m', date) AS month, SUM(duration_minutes) AS m, COUNT(*) AS c
            FROM pomodoro_records
            WHERE date BETWEEN ? AND ? AND status='completed'
        """
        params = [from_date.isoformat(), to_date.isoformat()]
        if tag:
            sql += " AND tag = ?"
            params.append(tag)
        sql += " GROUP BY month ORDER BY month"
        rows = db.execute(sql, params).fetchall()
        return jsonify({
            'data': [{'period': r['month'], 'minutes': r['m'], 'count': r['c']} for r in rows],
            'goal_minutes': goal_minutes * 30,
        })

    return jsonify({'data': [], 'goal_minutes': goal_minutes})

# --- 导出 API ---

@app.route('/api/export', methods=['GET'])
def api_export():
    db = get_db()
    fmt = request.args.get('format', 'json')
    rows = db.execute("""
        SELECT id, date, start_time, duration_minutes, status, tag, focus_score, reflection
        FROM pomodoro_records ORDER BY start_time
    """).fetchall()
    records = [dict(r) for r in rows]

    if fmt == 'csv':
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'id', 'date', 'start_time', 'duration_minutes', 'status',
            'tag', 'focus_score', 'reflection'
        ])
        writer.writeheader()
        writer.writerows(records)
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename=pomodoro_export.csv',
        }

    return jsonify(records)

# --- 备份 API ---

@app.route('/api/backup', methods=['GET'])
def api_backup():
    """下载 pomodoro.db 的 zip 备份"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(str(DB_PATH), 'pomodoro.db')
    buf.seek(0)
    return buf.getvalue(), 200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename=pomodoro_backup.zip',
    }

@app.route('/api/open-data-folder', methods=['POST'])
def api_open_data_folder():
    """打开数据目录"""
    folder = str(BASE_DIR)
    try:
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.run(['open', folder])
        else:
            subprocess.run(['xdg-open', folder])
        return jsonify({'ok': True, 'path': folder})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# --- 数据库路径 API ---

@app.route('/api/data-path', methods=['GET'])
def api_data_path():
    """返回数据库路径"""
    return jsonify({
        'db_path': str(DB_PATH),
        'folder': str(BASE_DIR),
    })

# ── 目标体系 ──────────────────────────────────────────

GOALS = [
    {"id": 1, "name": "GPA 3.7+ 重修翻盘", "icon": "🎓", "totalPomo": 2000, "color": "#E74C3C",
     "keywords": ["概率论", "高数", "线性代数", "统计", "算法", "基因组", "C语言", "Linux", "细胞", "芯片", "测序", "模式识别", "遗传", "肿瘤", "高等数学", "多元统计", "生物信息学算法"]},
    {"id": 2, "name": "雅思 7.5+", "icon": "🇬🇧", "totalPomo": 600, "color": "#2980B9",
     "keywords": ["雅思", "英语", "词汇", "听力", "口语", "写作", "剑雅", "阅读", "单词"]},
    {"id": 3, "name": "6个 GitHub 项目", "icon": "💻", "totalPomo": 480, "color": "#27AE60",
     "keywords": ["GitHub", "项目", "Python", "代码", "编程", "CNN", "PyTorch", "Spring", "DICOM", "RNA-seq", "scRNA", "Drug", "Multi-omics"]},
    {"id": 4, "name": "GRE 320+", "icon": "🧠", "totalPomo": 400, "color": "#8E44AD",
     "keywords": ["GRE", "词汇", "数学", "刷题"]},
    {"id": 5, "name": "科研实验室深度参与", "icon": "🔬", "totalPomo": 300, "color": "#E67E22",
     "keywords": ["课题组", "科研", "论文", "实验", "实验室", "导师"]},
    {"id": 6, "name": "LeetCode 200题", "icon": "💼", "totalPomo": 200, "color": "#1ABC9C",
     "keywords": ["LeetCode", "刷题", "算法", "数据结构", "DP"]},
    {"id": 7, "name": "体脂 15%–20%", "icon": "🏃", "totalPomo": 200, "color": "#E91E90",
     "keywords": ["健身", "运动", "跑步", "快走", "训练", "拉伸"]},
    {"id": 8, "name": "德语 A2", "icon": "🇩🇪", "totalPomo": 200, "color": "#F1C40F",
     "keywords": ["德语", "German"]},
    {"id": 9, "name": "阅读积累", "icon": "📖", "totalPomo": 100, "color": "#34495E",
     "keywords": ["阅读", "读书", "穷查理"]},
]

@app.route('/api/goals', methods=['GET'])
def api_get_goals():
    """返回目标体系 + 当前进度"""
    db = get_db()
    goals_with_progress = []
    for g in GOALS:
        # 统计已完成番茄数：匹配任意关键词的 tag 的总 completed 番茄数
        done = 0
        for kw in g['keywords']:
            row = db.execute("""
                SELECT COALESCE(SUM(duration_minutes), 0) AS total_min
                FROM pomodoro_records
                WHERE status = 'completed' AND tag LIKE ?
            """, (f'%{kw}%',)).fetchone()
            done += row['total_min']
        # 按 25min 一个番茄换算
        done_pomo = round(done / 25)
        pct = min(100, round(done_pomo / g['totalPomo'] * 100, 1)) if g['totalPomo'] > 0 else 0
        goals_with_progress.append({
            **g,
            'donePomo': done_pomo,
            'pct': pct,
        })
    return jsonify({'goals': goals_with_progress})


# ── 每日待办任务 API ─────────────────────────────────────

# CSV 每日待办文件夹路径（与 first-cc 相邻的 TUM申请 目录）
_CSV_TASKS_DIR = None

def _get_csv_tasks_dir():
    global _CSV_TASKS_DIR
    if _CSV_TASKS_DIR is None:
        candidate = BASE_DIR.parent / 'TUM申请' / '每日待办'
        if candidate.exists():
            _CSV_TASKS_DIR = candidate
        else:
            _CSV_TASKS_DIR = BASE_DIR / '每日待办'  # fallback
    return _CSV_TASKS_DIR

def parse_task_csv(filepath):
    """解析待办 CSV，返回任务列表（不含完成状态）"""
    tasks = []
    if not filepath.exists():
        return tasks
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header_skipped = False
        for i, row in enumerate(reader):
            if not row or not any(cell.strip() for cell in row):
                continue
            if row[0].startswith('#'):
                continue
            # 跳过 CSV 表头行
            if not header_skipped and row[0].strip().lower().startswith('task name'):
                header_skipped = True
                continue
            header_skipped = True
            name = row[0].strip() if len(row) > 0 else ''
            domain = row[2].strip() if len(row) > 2 else ''
            est_time = row[3].strip() if len(row) > 3 else ''
            pomo_str = row[4].strip() if len(row) > 4 else '0'
            priority = row[5].strip() if len(row) > 5 else '🟡Medium'
            try:
                pomo_count = int(pomo_str) if pomo_str else 0
            except ValueError:
                pomo_count = 0
            if not name:
                continue
            tasks.append({
                'index': len(tasks),
                'name': name,
                'domain': domain,
                'estTime': est_time,
                'pomodoroCount': pomo_count,
                'priority': priority,
            })
    return tasks

@app.route('/api/daily-tasks', methods=['GET'])
def api_daily_tasks():
    """读取当日待办 CSV + 合并标签完成状态"""
    db = get_db()
    date = request.args.get('date', datetime.date.today().isoformat())
    csv_dir = _get_csv_tasks_dir()
    filepath = csv_dir / f'{date}.csv'

    tasks = parse_task_csv(filepath)

    if not tasks:
        return jsonify({'date': date, 'tasks': [], 'hasCsv': False})

    # 查询所有 tag_type='once' 的标签及其今日完成数
    today = datetime.date.today().isoformat()
    once_tags = {}
    for r in db.execute("""
        SELECT t.name, t.target_pomodoros, t.id,
               (SELECT COUNT(*) FROM pomodoro_records pr
                WHERE pr.tag = t.name AND pr.date = ? AND pr.status = 'completed') AS today_done,
               (SELECT COUNT(*) FROM pomodoro_records pr
                WHERE pr.tag = t.name AND pr.status = 'completed') AS all_done
        FROM tags t WHERE t.tag_type = 'once'
    """, (today,)).fetchall():
        once_tags[r['name']] = {'id': r['id'], 'today_done': r['today_done'],
                                 'all_done': r['all_done'], 'target': r['target_pomodoros'] or 0}

    # 合并状态
    for task in tasks:
        tinfo = once_tags.get(task['name'])
        if tinfo and tinfo['target'] > 0:
            task['tagId'] = tinfo['id']
            task['donePomodoros'] = tinfo['today_done']
            task['targetPomodoros'] = tinfo['target']
            task['done'] = tinfo['today_done'] >= tinfo['target']
        else:
            task['tagId'] = None
            task['donePomodoros'] = 0
            task['targetPomodoros'] = task['pomodoroCount']
            task['done'] = False

    # CSV header 的 Status 列不作为状态源

    return jsonify({
        'date': date,
        'tasks': tasks,
        'hasCsv': True,
    })

@app.route('/api/daily-tasks/toggle', methods=['POST'])
def api_daily_tasks_toggle():
    """手动切换任务完成状态"""
    db = get_db()
    data = request.get_json() or {}
    task_name = (data.get('name') or '').strip()
    pomodoro_count = data.get('pomodoroCount', 0)
    mark_done = data.get('done', False)

    if not task_name:
        return jsonify({'ok': False, 'error': '任务名不能为空'}), 400

    now = datetime.datetime.now().isoformat()
    existing = db.execute("SELECT * FROM tags WHERE name = ? AND tag_type = 'once'",
                          (task_name,)).fetchone()

    if mark_done:
        if not existing:
            db.execute("""
                INSERT INTO tags (name, color, icon, target_pomodoros, tag_type, created_at)
                VALUES (?, ?, ?, ?, 'once', ?)
            """, (task_name, '#27AE60', '', pomodoro_count if pomodoro_count > 0 else None, now))
        db.commit()
        return jsonify({'ok': True, 'action': 'created'})
    else:
        if existing:
            db.execute("DELETE FROM tags WHERE id = ?", (existing['id'],))
            db.commit()
        return jsonify({'ok': True, 'action': 'deleted'})

@app.route('/api/daily-tasks/history', methods=['GET'])
def api_daily_tasks_history():
    """返回有 CSV 文件的日期列表"""
    csv_dir = _get_csv_tasks_dir()
    dates = []
    if csv_dir.exists():
        for f in sorted(csv_dir.glob('*.csv'), reverse=True):
            name = f.stem  # YYYY-MM-DD
            if len(name) == 10 and name[4] == '-' and name[7] == '-':
                dates.append(name)
    today = datetime.date.today().isoformat()
    return jsonify({
        'dates': dates,
        'today': today,
    })


# ── JS-API 桥接 ────────────────────────────────────────────

class Api:
    """暴露给前端 JS 的方法，通过 window.pywebview.api 调用"""
    def minimize(self):
        """最小化主窗口"""
        try:
            import webview
            win = webview.windows[0]
            win.minimize()
        except Exception:
            pass

    def close_app(self):
        """退出应用"""
        os._exit(0)

    def show_mini(self):
        """显示圆形悬浮窗"""
        threading.Thread(target=_show_mini_window, daemon=True).start()

    def hide_mini(self):
        """关闭圆形悬浮窗"""
        global _mini_window
        if _mini_window:
            try:
                _mini_window.destroy()
            except Exception:
                pass
            _mini_window = None

    def get_timer_state(self):
        """返回当前计时状态（供迷你窗获取）"""
        return _timer_state

    def update_timer_state(self, state):
        """主窗口同步状态到服务端"""
        global _timer_state
        if state:
            for k in _TIMER_STATE_KEYS:
                if k in state:
                    _timer_state[k] = state[k]

_mini_window = None

def _show_mini_window():
    """创建圆形悬浮窗（非阻塞，在独立线程中）"""
    global _mini_window
    try:
        import webview
        if _mini_window:
            try:
                _mini_window.destroy()
            except Exception:
                pass
        _mini_window = webview.create_window(
            title='Tomato Mini',
            url=f'http://{HOST}:{PORT}/mini',
            width=210,
            height=240,
            frameless=True,
            on_top=True,
            resizable=False,
            transparent=False,
        )
        _mini_window.set_on_top(True)
        webview.start()
    except Exception:
        _mini_window = None

# ── 系统托盘 ──────────────────────────────────────────────

def create_tray_icon():
    """创建系统托盘图标，返回 (icon, tray) 或 (None, None)"""
    try:
        from PIL import Image, ImageDraw
        import pystray
    except ImportError:
        return None, None

    # 优先使用下载的图标，否则代码绘制
    icon_file = BASE_DIR / 'static' / 'icon.png'
    if icon_file.exists():
        img = Image.open(icon_file).resize((64, 64), Image.LANCZOS)
    else:
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 8, 60, 60], fill='#E74C3C', outline='#C0392B', width=2)
        draw.ellipse([20, 4, 44, 20], fill='#27AE60', outline='#1E8449', width=1)

    def on_open(icon, item):
        webbrowser.open(f'http://{HOST}:{PORT}')

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        'pomodoro',
        img,
        '🍅 番茄钟',
        menu=pystray.Menu(
            pystray.MenuItem('打开番茄钟', on_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', on_quit),
        ),
    )
    return icon, pystray

# ── 主入口 ────────────────────────────────────────────────

def safe_print(msg):
    """Windows GBK 兼容打印"""
    try:
        print(msg)
    except UnicodeEncodeError:
        sanitized = msg.encode('gbk', errors='replace').decode('gbk', errors='replace')
        print(sanitized)

def _start_flask():
    """后台线程启动 Flask"""
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

def run_browser_mode():
    """开发模式：浏览器打开"""
    init_db()
    safe_print("[Pomodoro] Starting (browser mode)...")
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()
    safe_print(f"   http://{HOST}:{PORT}")
    webbrowser.open(f'http://{HOST}:{PORT}')

    icon, pystray_mod = create_tray_icon()
    if icon and pystray_mod:
        icon.run()
    else:
        safe_print("   (Ctrl+C to quit)")
        flask_thread.join()

def run_desktop_mode():
    """桌面模式：pywebview 原生窗口"""
    import webview

    init_db()
    safe_print("[Pomodoro] Starting (desktop mode)...")

    # 启动 Flask
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()

    # 创建无边框原生窗口
    icon_file = BASE_DIR / 'static' / 'tomato.ico'
    webview.create_window(
        title='Tomato Timer',
        url=f'http://{HOST}:{PORT}',
        width=480,
        height=780,
        min_size=(320, 480),
        frameless=True,
        easy_drag=True,
        text_select=False,
        js_api=Api(),
        **({'icon': str(icon_file)} if icon_file.exists() else {}),
    )

    # 窗口关闭时退出
    webview.start()
    os._exit(0)

def run_headless_mode():
    """Electron 模式：纯后台 Flask，供 Electron 窗口加载"""
    init_db()
    safe_print(f"[Pomodoro] Headless — http://{HOST}:{PORT}")
    _start_flask()

def main():
    if '--headless' in sys.argv:
        run_headless_mode()
    elif '--browser' in sys.argv:
        run_browser_mode()
    else:
        run_desktop_mode()

if __name__ == '__main__':
    main()

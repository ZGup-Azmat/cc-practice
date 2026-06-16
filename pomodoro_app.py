#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄钟 v5 — 纯 Tkinter 桌面应用
计时器 · 任务 · 看板 · 目标 · 设置 · 系统托盘
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import csv
import os
import sys
import time
import datetime
import threading
import io
import zipfile
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / 'pomodoro.db'
ICON_PATH = BASE_DIR / 'static' / 'tomato.ico'
PNG_PATH = BASE_DIR / 'static' / 'icon.png'
CSV_DIR = BASE_DIR.parent / 'TUM申请' / '每日待办'
if not CSV_DIR.exists():
    CSV_DIR = BASE_DIR / '每日待办'

# ── 常量 ─────────────────────────────────────────────────
WORK_TIME = 25 * 60
SHORT_BREAK = 5 * 60
LONG_BREAK = 15 * 60
POMODOROS_BEFORE_LONG = 4

FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")
FONT_TIMER = ("Consolas", 42, "bold")
FONT_LABEL = ("Microsoft YaHei UI", 11)
FONT_BUTTON = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)

PRESET_COLORS = ['#E74C3C','#E67E22','#F1C40F','#27AE60','#1ABC9C','#2980B9','#8E44AD','#E91E90']

THEMES = {
    "light": {"bg":"#F5F6FA","card":"#FFFFFF","text":"#2C3E50","sub":"#64748B","muted":"#94A3B8","border":"#E2E8F0","accent":"#E74C3C","green":"#27AE60","blue":"#2980B9","orange":"#E67E22","ring_bg":"#E8E8E8"},
    "dark":  {"bg":"#0D1117","card":"#161B22","text":"#C9D1D9","sub":"#8B949E","muted":"#484F58","border":"#30363D","accent":"#FF6B6B","green":"#3FB950","blue":"#58A6FF","orange":"#D29922","ring_bg":"#21262D"},
}

GOALS = [
    {"id":1,"name":"GPA 3.7+ 重修翻盘","icon":"🎓","totalPomo":2000,"color":"#E74C3C","keywords":["概率论","高数","线性代数","统计","算法","基因组","C语言","Linux","细胞","芯片","测序","模式识别","遗传","肿瘤","高等数学","多元统计","生物信息学算法"]},
    {"id":2,"name":"雅思 7.5+","icon":"🇬🇧","totalPomo":600,"color":"#2980B9","keywords":["雅思","英语","词汇","听力","口语","写作","剑雅","阅读","单词"]},
    {"id":3,"name":"6个 GitHub 项目","icon":"💻","totalPomo":480,"color":"#27AE60","keywords":["GitHub","项目","Python","代码","编程","CNN","PyTorch","Spring"]},
    {"id":4,"name":"GRE 320+","icon":"🧠","totalPomo":400,"color":"#8E44AD","keywords":["GRE","词汇","数学","刷题"]},
    {"id":5,"name":"科研实验室深度参与","icon":"🔬","totalPomo":300,"color":"#E67E22","keywords":["课题组","科研","论文","实验","实验室","导师"]},
    {"id":6,"name":"LeetCode 200题","icon":"💼","totalPomo":200,"color":"#1ABC9C","keywords":["LeetCode","刷题","数据结构","DP"]},
    {"id":7,"name":"体脂 15%–20%","icon":"🏃","totalPomo":200,"color":"#E91E90","keywords":["健身","运动","跑步","快走","训练","拉伸"]},
    {"id":8,"name":"德语 A2","icon":"🇩🇪","totalPomo":200,"color":"#F1C40F","keywords":["德语","German"]},
    {"id":9,"name":"阅读积累","icon":"📖","totalPomo":100,"color":"#34495E","keywords":["阅读","读书","穷查理"]},
]

# ── 数据库管理 ──────────────────────────────────────────
class DBManager:
    def __init__(self, path):
        self.path = str(path)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pomodoro_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, start_time TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('completed','abandoned')),
                tag TEXT DEFAULT '', focus_score INTEGER DEFAULT NULL, reflection TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS idx_date ON pomodoro_records(date);
            CREATE INDEX IF NOT EXISTS idx_tag ON pomodoro_records(tag);
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#27AE60', icon TEXT DEFAULT '', created_at TEXT NOT NULL,
                target_pomodoros INTEGER DEFAULT NULL, tag_type TEXT DEFAULT 'daily');
        """)
        # 列兼容
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tags)")}
        if 'target_pomodoros' not in cols:
            conn.execute("ALTER TABLE tags ADD COLUMN target_pomodoros INTEGER DEFAULT NULL")
        if 'tag_type' not in cols:
            conn.execute("ALTER TABLE tags ADD COLUMN tag_type TEXT DEFAULT 'daily'")
        # 仅在 tags 空时迁移
        if conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0:
            conn.execute("INSERT OR IGNORE INTO tags(name,color,icon,created_at) SELECT DISTINCT tag,'#27AE60','',datetime('now') FROM pomodoro_records WHERE tag!=''")
        for k,v in {'work_duration':'25','short_break_duration':'5','long_break_duration':'15','pomodoros_before_long':'4','daily_goal_minutes':'120','theme':'light','last_tag':''}.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
        conn.commit()
        conn.close()

    def get_setting(self, key):
        conn = self._conn()
        r = conn.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        conn.close()
        return r['value'] if r else None

    def set_setting(self, key, value):
        conn = self._conn()
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(key,str(value)))
        conn.commit()
        conn.close()

    def get_all_settings(self):
        conn = self._conn()
        rows = conn.execute("SELECT key,value FROM settings").fetchall()
        conn.close()
        return {r['key']:r['value'] for r in rows}

    def create_record(self, date, start_time, duration_minutes, status, tag='', focus_score=None, reflection=''):
        conn = self._conn()
        conn.execute("INSERT INTO pomodoro_records(date,start_time,duration_minutes,status,tag,focus_score,reflection) VALUES(?,?,?,?,?,?,?)",
                     (date,start_time,duration_minutes,status,tag,focus_score,reflection))
        conn.commit()
        conn.close()

    def today_stats(self):
        conn = self._conn()
        today = datetime.date.today().isoformat()
        r = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) AS m, COUNT(*) AS c FROM pomodoro_records WHERE date=? AND status='completed'",(today,)).fetchone()
        goal = conn.execute("SELECT value FROM settings WHERE key='daily_goal_minutes'").fetchone()
        conn.close()
        gm = int(goal['value']) if goal else 120
        return {'total_minutes':r['m'],'pomodoro_count':r['c'],'goal_minutes':gm,'goal_percent':round(r['m']/gm*100,1)}

    def all_tags(self):
        conn = self._conn()
        today = datetime.date.today().isoformat()
        rows = conn.execute("SELECT * FROM tags ORDER BY created_at").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            td = conn.execute("SELECT COUNT(*) FROM pomodoro_records WHERE date=? AND status='completed' AND tag=?",(today,d['name'])).fetchone()[0]
            ad = conn.execute("SELECT COUNT(*) FROM pomodoro_records WHERE status='completed' AND tag=?",(d['name'],)).fetchone()[0]
            d['today_done'] = td
            d['all_done'] = ad
            result.append(d)
        conn.close()
        return result

    def create_tag(self, name, color='#27AE60', icon='', target_pomodoros=None, tag_type='daily'):
        conn = self._conn()
        conn.execute("INSERT INTO tags(name,color,icon,target_pomodoros,tag_type,created_at) VALUES(?,?,?,?,?,?)",
                     (name,color,icon,target_pomodoros,tag_type,datetime.datetime.now().isoformat()))
        conn.commit()
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return rid

    def delete_tag(self, tag_id):
        conn = self._conn()
        conn.execute("DELETE FROM tags WHERE id=?",(tag_id,))
        conn.commit()
        conn.close()

    def update_tag(self, tag_id, name, color, icon, target_pomodoros, tag_type):
        conn = self._conn()
        conn.execute("UPDATE tags SET name=?,color=?,icon=?,target_pomodoros=?,tag_type=? WHERE id=?",
                     (name,color,icon,target_pomodoros,tag_type,tag_id))
        conn.commit()
        conn.close()

    def get_goals_progress(self):
        conn = self._conn()
        all_kw = list({kw for g in GOALS for kw in g['keywords']})
        if not all_kw:
            conn.close(); return []
        clauses = " OR ".join(["tag LIKE ?"]*len(all_kw))
        params = [f'%{kw}%' for kw in all_kw]
        rows = conn.execute(f"SELECT tag, SUM(duration_minutes) AS m FROM pomodoro_records WHERE status='completed' AND ({clauses}) GROUP BY tag", params).fetchall()
        tag_min = {r['tag']:r['m'] for r in rows}
        conn.close()
        result = []
        for g in GOALS:
            done_pomo = round(sum(tag_min.get(t,0) for t in tag_min if any(kw in t for kw in g['keywords']))/25)
            pct = min(100,round(done_pomo/g['totalPomo']*100,1)) if g['totalPomo']>0 else 0
            result.append({**g,'donePomo':done_pomo,'pct':pct})
        return result

    def heatmap_data(self, view='year', year=None, month=None, tag=None):
        conn = self._conn()
        today = datetime.date.today()
        year = year or today.year
        if view=='month':
            month = month or today.month
            fd = datetime.date(year,month,1)
            if month==12: td=datetime.date(year+1,1,1)
            else: td=datetime.date(year,month+1,1)
        else:
            fd = datetime.date(year,1,1); td=datetime.date(year+1,1,1)
        sql = "SELECT date, SUM(duration_minutes) AS m, COUNT(*) AS c FROM pomodoro_records WHERE date>=? AND date<? AND status='completed'"
        params = [fd.isoformat(),td.isoformat()]
        if tag: sql+=" AND tag=?"; params.append(tag)
        sql+=" GROUP BY date"
        rows = conn.execute(sql,params).fetchall()
        conn.close()
        return {r['date']:{'minutes':r['m'],'count':r['c']} for r in rows}, fd, td

    def trend_data(self, days=90, tag=None):
        conn = self._conn()
        today = datetime.date.today()
        fd = today - datetime.timedelta(days=days)
        params = [fd.isoformat(),today.isoformat()]
        sql = "SELECT date, SUM(duration_minutes) AS m FROM pomodoro_records WHERE date BETWEEN ? AND ? AND status='completed'"
        if tag: sql+=" AND tag=?"; params.append(tag)
        sql+=" GROUP BY date ORDER BY date"
        rows = conn.execute(sql,params).fetchall()
        conn.close()
        dmap = {r['date']:r['m'] for r in rows}
        result = []
        cur = fd
        while cur<=today:
            iso = cur.isoformat()
            result.append({'date':iso,'minutes':dmap.get(iso,0)})
            cur+=datetime.timedelta(days=1)
        return result

    def summary(self):
        conn = self._conn()
        today = datetime.date.today()
        tr = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) AS m, COUNT(*) AS c FROM pomodoro_records WHERE date=? AND status='completed'",(today.isoformat(),)).fetchone()
        ws = today-datetime.timedelta(days=today.weekday())
        wr = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) AS m FROM pomodoro_records WHERE date BETWEEN ? AND ? AND status='completed'",(ws.isoformat(),(ws+datetime.timedelta(days=6)).isoformat())).fetchone()
        mr = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) AS m FROM pomodoro_records WHERE date BETWEEN ? AND ? AND status='completed'",(today.replace(day=1).isoformat(),today.isoformat())).fetchone()
        streak=0; cur=today
        while conn.execute("SELECT COUNT(*) AS c FROM pomodoro_records WHERE date=? AND status='completed'",(cur.isoformat(),)).fetchone()['c']>0:
            streak+=1; cur-=datetime.timedelta(days=1)
        total = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) FROM pomodoro_records WHERE status='completed'").fetchone()[0]
        tags = conn.execute("SELECT tag,COUNT(*) AS c,SUM(duration_minutes) AS m FROM pomodoro_records WHERE status='completed' AND tag!='' GROUP BY tag ORDER BY c DESC LIMIT 3").fetchall()
        conn.close()
        return {'today':{'total_minutes':tr['m'],'pomodoro_count':tr['c']},'week':{'total_minutes':wr['m']},'month':{'total_minutes':mr['m']},'streak':streak,'total':total,'top_tags':[dict(t) for t in tags]}

    def by_tag(self, period='all'):
        conn = self._conn()
        today = datetime.date.today()
        sql = "SELECT tag,COUNT(*) AS cnt, SUM(duration_minutes) AS total_min FROM pomodoro_records WHERE status='completed' AND tag!=''"
        params = []
        if period=='today': sql+=" AND date=?"; params.append(today.isoformat())
        elif period=='week': sql+=" AND date>=?"; params.append((today-datetime.timedelta(days=today.weekday())).isoformat())
        elif period=='month': sql+=" AND date>=?"; params.append(today.replace(day=1).isoformat())
        sql+=" GROUP BY tag ORDER BY total_min DESC"
        rows = conn.execute(sql,params).fetchall()
        tag_colors = {r['name']:r for r in conn.execute("SELECT name,color,icon FROM tags")}
        conn.close()
        return [{'tag':r['tag'],'count':r['cnt'],'total_minutes':r['total_min'],'color':tag_colors.get(r['tag'],{}).get('color','#94A3B8'),'icon':tag_colors.get(r['tag'],{}).get('icon','')} for r in rows]

    def export_csv(self):
        conn = self._conn()
        rows = conn.execute("SELECT * FROM pomodoro_records ORDER BY start_time").fetchall()
        conn.close()
        out = io.StringIO()
        w = csv.DictWriter(out,fieldnames=['id','date','start_time','duration_minutes','status','tag','focus_score','reflection'])
        w.writeheader(); w.writerows([dict(r) for r in rows])
        return out.getvalue()

    def export_json(self):
        import json
        conn = self._conn()
        rows = conn.execute("SELECT * FROM pomodoro_records ORDER BY start_time").fetchall()
        conn.close()
        return json.dumps([dict(r) for r in rows],ensure_ascii=False,indent=2)

    def backup(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as zf:
            zf.write(self.path,'pomodoro.db')
        buf.seek(0)
        return buf.getvalue()


# ── 主应用 ──────────────────────────────────────────────
class PomodoroApp:
    def __init__(self):
        self.db = DBManager(DB_PATH)
        self.root = tk.Tk()
        self.root.title("🍅 番茄钟 v5")
        self.root.geometry("500x700")
        self.root.minsize(420,600)
        try: self.root.iconbitmap(default=str(ICON_PATH))
        except: pass

        # 主题
        self.theme_name = self.db.get_setting('theme') or 'light'
        self.T = THEMES[self.theme_name]

        # 计时状态
        self.mode = 'work'
        self.time_left = WORK_TIME
        self.total_time = WORK_TIME
        self.running = False
        self.pomodoro_count = 0
        self.session_start = None
        self.tick_after = None
        self.selected_tag = None
        self.active_task_index = None

        # 加载设置
        self.settings = self.db.get_all_settings()

        # 容器
        self.main = tk.Frame(self.root, bg=self.T['bg'])
        self.main.pack(fill=tk.BOTH, expand=True)

        # Notebook
        style = ttk.Style()
        style.theme_use('clam')
        self.notebook = ttk.Notebook(self.main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # 构建 5 个 Tab
        self.timer_frame = tk.Frame(self.notebook, bg=self.T['bg'])
        self.tasks_frame = tk.Frame(self.notebook, bg=self.T['bg'])
        self.dash_frame = tk.Frame(self.notebook, bg=self.T['bg'])
        self.goals_frame = tk.Frame(self.notebook, bg=self.T['bg'])
        self.settings_frame = tk.Frame(self.notebook, bg=self.T['bg'])

        self.notebook.add(self.timer_frame, text="⏱ 计时")
        self.notebook.add(self.tasks_frame, text="📋 任务")
        self.notebook.add(self.dash_frame, text="📊 看板")
        self.notebook.add(self.goals_frame, text="🎯 目标")
        self.notebook.add(self.settings_frame, text="⚙ 设置")

        # 所有需要主题同步的控件
        self._theme_widgets = []

        self._build_timer()
        self._build_tasks()
        self._build_dashboard()
        self._build_goals()
        self._build_settings()

        self._update_display()

        # 窗口居中
        self.root.update_idletasks()
        w, h = 500, 700
        x = (self.root.winfo_screenwidth()-w)//2
        y = (self.root.winfo_screenheight()-h)//2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # 关闭处理
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 加载任务 CSV
        self.root.after(500, self._load_tasks_for_today)

    # ── 主题工具 ────────────────────────────────────────
    def _fbg(self, parent, **kw):
        f = tk.Frame(parent, bg=self.T['card'], **kw)
        self._theme_widgets.append(('bg',f,self.T['card']))
        return f

    def _flbl(self, parent, txt, font=FONT_LABEL, fg=None, **kw):
        lbl = tk.Label(parent, text=txt, font=font, fg=fg or self.T['text'], bg=self.T['card'], **kw)
        self._theme_widgets.append(('bg',lbl,self.T['card']))
        self._theme_widgets.append(('fg',lbl,fg or self.T['text']))
        return lbl

    def _apply_theme(self):
        self.T = THEMES[self.theme_name]
        self.main.configure(bg=self.T['bg'])
        self.timer_frame.configure(bg=self.T['bg'])
        self.tasks_frame.configure(bg=self.T['bg'])
        self.dash_frame.configure(bg=self.T['bg'])
        self.goals_frame.configure(bg=self.T['bg'])
        self.settings_frame.configure(bg=self.T['bg'])
        for attr, widget, val in self._theme_widgets:
            try:
                if attr == 'bg': widget.configure(bg=self.T[val] if val in self.T else val)
                elif attr == 'fg': widget.configure(fg=self.T[val] if val in self.T else val)
            except: pass
        if hasattr(self,'dash_canvas'):
            self.dash_canvas.configure(bg=self.T['card'])
        self._update_display()

    # ══════════════ ⏱ 计时页 ══════════════
    def _build_timer(self):
        f = self.timer_frame
        # 每日目标
        self.goal_frame = self._fbg(f)
        self.goal_frame.pack(fill=tk.X, padx=16, pady=(12,0))
        self.goal_label = self._flbl(self.goal_frame, "🎯 今日目标", font=FONT_SMALL, fg=self.T['sub'])
        self.goal_label.pack(side=tk.LEFT)
        self.goal_text = self._flbl(self.goal_frame, "0h 0m / 2h 0m", font=FONT_SMALL, fg=self.T['sub'])
        self.goal_text.pack(side=tk.RIGHT)
        self.goal_bar = tk.Canvas(self.goal_frame, height=8, bg=self.T['card'], highlightthickness=0)
        self.goal_bar.pack(fill=tk.X, pady=(6,0))

        # 任务名
        self.task_name_label = tk.Label(f, text="", font=FONT_LABEL, fg=self.T['accent'], bg=self.T['bg'])
        self.task_name_label.pack(pady=(8,0))

        # Canvas 圆环
        self.canvas_size = 260
        self.canvas = tk.Canvas(f, width=self.canvas_size, height=self.canvas_size, bg=self.T['bg'], highlightthickness=0)
        self.canvas.pack(pady=(8,4))
        self.timer_text_id = self.canvas.create_text(self.canvas_size//2, self.canvas_size//2-15, text="25:00", font=FONT_TIMER, fill=self.T['text'])
        self.mode_text_id = self.canvas.create_text(self.canvas_size//2, self.canvas_size//2+38, text="🍅 准备开始", font=FONT_LABEL, fill=self.T['accent'])
        self.phase_text_id = self.canvas.create_text(self.canvas_size//2, self.canvas_size//2+60, text="", font=FONT_SMALL, fill=self.T['muted'])
        self._draw_ring(1.0)

        # 按钮
        btnf = tk.Frame(f, bg=self.T['bg'])
        btnf.pack(pady=(10,4))
        self.start_btn = tk.Button(btnf, text="▶  开始", font=FONT_BUTTON, bg=self.T['accent'], fg='white', relief=tk.FLAT, padx=18, pady=8, cursor="hand2", command=self._toggle_timer)
        self.start_btn.pack(side=tk.LEFT, padx=4)
        self.stop_btn = tk.Button(btnf, text="⏹  停止", font=FONT_BUTTON, bg=self.T['muted'], fg='white', relief=tk.FLAT, padx=18, pady=8, cursor="hand2", command=self._stop_timer)
        self.stop_btn.pack(side=tk.LEFT, padx=4)
        self.skip_btn = tk.Button(btnf, text="⏭  跳过", font=FONT_BUTTON, bg=self.T['muted'], fg='white', relief=tk.FLAT, padx=18, pady=8, cursor="hand2", command=self._skip)
        self.skip_btn.pack(side=tk.LEFT, padx=4)

        # 统计
        statf = tk.Frame(f, bg=self.T['bg'])
        statf.pack(pady=(8,0))
        self.count_label = tk.Label(statf, text="✅ 0 个番茄 | 📅 今日 0 个", font=FONT_SMALL, fg=self.T['sub'], bg=self.T['bg'])
        self.count_label.pack()

    def _draw_ring(self, fraction=1.0):
        self.canvas.delete("ring")
        cx, cy, r, w = self.canvas_size//2, self.canvas_size//2, 100, 8
        self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r, outline=self.T['ring_bg'], width=w, tags="ring")
        if fraction>0:
            angle = 360.0*fraction
            self.canvas.create_arc(cx-r,cy-r,cx+r,cy+r, start=90, extent=-angle, style=tk.ARC, outline=self.T['accent'], width=w, tags="ring")

    def _update_display(self):
        c = self.T
        mins, secs = self.time_left//60, self.time_left%60
        self.canvas.itemconfig(self.timer_text_id, text=f"{mins:02d}:{secs:02d}", fill=c['text'])
        mode_labels = {'work':'🍅 专注工作中','short_break':'☕ 短休息','long_break':'🌴 长休息'}
        if self.selected_tag:
            prefix = '🍅 ' if self.running else '▶ '
            self.canvas.itemconfig(self.mode_text_id, text=prefix+self.selected_tag['name'], fill=c['accent'])
        else:
            self.canvas.itemconfig(self.mode_text_id, text=mode_labels.get(self.mode,'🍅 准备开始'), fill=c['accent'])
        self.task_name_label.config(text=self.selected_tag['name'] if self.selected_tag else '', fg=c['accent'])
        before_long = POMODOROS_BEFORE_LONG
        la = before_long-(self.pomodoro_count%before_long)
        phase = f"第 {self.pomodoro_count+1} 个番茄 | {la} 个后长休息" if self.mode=='work' else f"已完成 {self.pomodoro_count} 个番茄"
        self.canvas.itemconfig(self.phase_text_id, text=phase)
        self._draw_ring(self.time_left/self.total_time if self.total_time>0 else 0)
        if self.running:
            self.start_btn.config(text="⏸  暂停", bg=self.T['orange'])
            self.stop_btn.config(state=tk.NORMAL)
            self.skip_btn.config(state=tk.DISABLED)
        else:
            self.start_btn.config(text="▶  开始", bg=self.T['accent'])
            self.stop_btn.config(state=tk.DISABLED if self.time_left==self.total_time else tk.NORMAL)
            self.skip_btn.config(state=tk.NORMAL)
        self.canvas.configure(bg=self.T['bg'])

    # ── 计时引擎 ────────────────────────────────────
    def _toggle_timer(self):
        if self.running: self._pause()
        else: self._start()

    def _start(self):
        if not self.session_start:
            self.session_start = datetime.datetime.now().isoformat()
        self.running = True
        self._tick()

    def _pause(self):
        self.running = False
        if self.tick_after:
            self.root.after_cancel(self.tick_after)
            self.tick_after = None
        self._update_display()

    def _tick(self):
        if not self.running: return
        if self.time_left>0:
            self.time_left-=1
            self._update_display()
            self.tick_after = self.root.after(1000, self._tick)
        else:
            self.running = False
            self._on_timer_end()

    def _on_timer_end(self):
        if self.mode=='work':
            self.pomodoro_count+=1
            elapsed = self.total_time//60
            self.db.create_record(datetime.date.today().isoformat(), self.session_start, elapsed, 'completed', self.selected_tag['name'] if self.selected_tag else '')
            self._notify("番茄完成!", f"已完成 {self.pomodoro_count} 个番茄。休息一下吧~")
            self.session_start = None
            self._refresh_goals_tab()
            self._refresh_dashboard()
            if self.pomodoro_count%POMODOROS_BEFORE_LONG==0:
                self._switch_mode('long_break')
            else:
                self._switch_mode('short_break')
        else:
            self._notify("休息结束!", "开始新的番茄吧！")
            self._switch_mode('work')

    def _switch_mode(self, new_mode):
        self.mode = new_mode
        self.running = False
        if self.tick_after: self.root.after_cancel(self.tick_after); self.tick_after=None
        times = {'work':WORK_TIME,'short_break':SHORT_BREAK,'long_break':LONG_BREAK}
        self.time_left = times[new_mode]
        self.total_time = times[new_mode]
        self._update_display()

    def _stop_timer(self):
        if not self.session_start: return
        elapsed = self.total_time-self.time_left
        self.running = False
        if self.tick_after: self.root.after_cancel(self.tick_after); self.tick_after=None
        if elapsed>=300:
            self.db.create_record(datetime.date.today().isoformat(), self.session_start, round(elapsed/60), 'completed', self.selected_tag['name'] if self.selected_tag else '')
        self.session_start = None
        self.time_left = WORK_TIME
        self.total_time = WORK_TIME
        self.active_task_index = None
        self.selected_tag = None
        self._update_display()
        self._refresh_tasks_tab()
        self._refresh_goals_tab()
        self._refresh_dashboard()

    def _skip(self):
        if self.mode=='work': self._switch_mode('short_break')
        else: self._switch_mode('work')

    def _notify(self, title, msg):
        try: messagebox.showinfo(title, msg)
        except: pass

    # ══════════════ 📋 任务页 ══════════════
    def _build_tasks(self):
        f = self.tasks_frame
        # 日期导航
        nav = self._fbg(f)
        nav.pack(fill=tk.X, padx=12, pady=(10,0))
        self.tasks_date_var = tk.StringVar(value=datetime.date.today().isoformat())
        tk.Button(nav, text="◀", font=FONT_SMALL, command=lambda: self._shift_task_date(-1), bg=self.T['card'], fg=self.T['text'], borderwidth=0, cursor="hand2").pack(side=tk.LEFT)
        self.tasks_date_label = self._flbl(nav, self.tasks_date_var.get(), font=FONT_TITLE)
        self.tasks_date_label.pack(side=tk.LEFT, padx=8)
        tk.Button(nav, text="▶", font=FONT_SMALL, command=lambda: self._shift_task_date(1), bg=self.T['card'], fg=self.T['text'], borderwidth=0, cursor="hand2").pack(side=tk.LEFT)
        tk.Button(nav, text="📅 今天", font=FONT_SMALL, command=self._load_tasks_for_today, bg=self.T['accent'], fg='white', borderwidth=0, cursor="hand2", padx=8, pady=2).pack(side=tk.RIGHT)

        # 快速创建
        qc = self._fbg(f)
        qc.pack(fill=tk.X, padx=12, pady=(8,0))
        self.qc_var = tk.BooleanVar(value=False)
        self.qc_toggle = tk.Button(qc, text="＋ 快速添加任务", font=FONT_SMALL, command=self._toggle_qc, bg=self.T['card'], fg=self.T['sub'], borderwidth=1, relief=tk.GROOVE, cursor="hand2")
        self.qc_toggle.pack(fill=tk.X)
        self.qc_panel = tk.Frame(qc, bg=self.T['card'])
        self.qc_entry = tk.Entry(self.qc_panel, font=FONT_LABEL, bg=self.T['bg'], fg=self.T['text'], insertbackground=self.T['text'], relief=tk.FLAT)
        self.qc_entry.pack(fill=tk.X, pady=(6,4)); self.qc_entry.insert(0,"")
        qctype = tk.Frame(self.qc_panel, bg=self.T['card'])
        qctype.pack()
        self.qc_type = tk.StringVar(value='once')
        for t, txt in [('once','✅ 一次性'),('daily','🔄 每日'),('long','📈 长期')]:
            tk.Radiobutton(qctype, text=txt, variable=self.qc_type, value=t, font=FONT_SMALL, bg=self.T['card'], fg=self.T['text'], selectcolor=self.T['card'], activebackground=self.T['card']).pack(side=tk.LEFT, padx=4)
        qc2 = tk.Frame(self.qc_panel, bg=self.T['card'])
        qc2.pack(pady=(4,6))
        self.qc_pomo = tk.Spinbox(qc2, from_=0, to=99, width=4, font=FONT_SMALL)
        self.qc_pomo.pack(side=tk.LEFT)
        tk.Label(qc2, text="个番茄 (每个25min)", font=FONT_SMALL, fg=self.T['muted'], bg=self.T['card']).pack(side=tk.LEFT, padx=4)
        tk.Button(qc2, text="▶ 创建并开始", font=FONT_SMALL, bg=self.T['accent'], fg='white', borderwidth=0, cursor="hand2", command=self._qc_submit).pack(side=tk.LEFT, padx=8)

        # 进度条
        self.tasks_prog_frame = self._fbg(f)
        self.tasks_prog_frame.pack(fill=tk.X, padx=12, pady=(8,0))
        self.tasks_prog_canvas = tk.Canvas(self.tasks_prog_frame, height=8, bg=self.T['card'], highlightthickness=0)
        self.tasks_prog_canvas.pack(fill=tk.X)
        self.tasks_prog_label = self._flbl(self.tasks_prog_frame, "0 / 0 已完成", font=FONT_SMALL, fg=self.T['sub'])

        # 任务列表 Canvas
        list_frame = tk.Frame(f, bg=self.T['bg'])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        self.tasks_canvas_w = tk.Canvas(list_frame, bg=self.T['bg'], highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tasks_canvas_w.yview)
        self.tasks_inner = tk.Frame(self.tasks_canvas_w, bg=self.T['bg'])
        self.tasks_inner.bind("<Configure>", lambda e: self.tasks_canvas_w.configure(scrollregion=self.tasks_canvas_w.bbox("all")))
        self.tasks_canvas_w.create_window((0,0), window=self.tasks_inner, anchor="nw")
        self.tasks_canvas_w.configure(yscrollcommand=scrollbar.set)
        self.tasks_canvas_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tasks_canvas_w.bind_all("<MouseWheel>", lambda e: self.tasks_canvas_w.yview_scroll(int(-1*(e.delta/120)), "units"))

    def _toggle_qc(self):
        if self.qc_var.get():
            self.qc_panel.pack_forget()
            self.qc_var.set(False)
        else:
            self.qc_panel.pack(fill=tk.X, pady=(6,0))
            self.qc_var.set(True)

    def _qc_submit(self):
        name = self.qc_entry.get().strip()
        if not name or len(name)>12: messagebox.showwarning("提示","任务名需 1-12 个字符"); return
        try: pc = int(self.qc_pomo.get())
        except: pc = 0
        tag_id = self.db.create_tag(name, PRESET_COLORS[hash(name)%8], '', pc if pc>0 else None, self.qc_type.get())
        self.qc_entry.delete(0,tk.END)
        self._toggle_qc()
        self._start_task_by_name(name)

    def _load_tasks_for_today(self):
        self.tasks_date_var.set(datetime.date.today().isoformat())
        self._refresh_tasks_tab()

    def _shift_task_date(self, delta):
        cur = self.tasks_date_var.get()
        try:
            d = datetime.date.fromisoformat(cur)+datetime.timedelta(days=delta)
            self.tasks_date_var.set(d.isoformat())
            self._refresh_tasks_tab()
        except: pass

    def _parse_csv(self, path):
        tasks = []
        if not os.path.exists(path): return tasks
        with open(path,'r',encoding='utf-8') as f:
            reader = csv.reader(f)
            skipped = False
            for row in reader:
                if not row or not any(c.strip() for c in row): continue
                if row[0].startswith('#'): continue
                if not skipped and row[0].strip().lower().startswith('task name'): skipped=True; continue
                skipped=True
                name = row[0].strip() if len(row)>0 else ''
                domain = row[2].strip() if len(row)>2 else ''
                est = row[3].strip() if len(row)>3 else ''
                pc_str = row[4].strip() if len(row)>4 else '0'
                pri = row[5].strip() if len(row)>5 else '🟡Medium'
                if not name: continue
                try: pc = int(pc_str) if pc_str else 0
                except: pc = 0
                tasks.append({'index':len(tasks),'name':name,'domain':domain,'estTime':est,'pomodoroCount':pc,'priority':pri,'done':False,'donePomodoros':0})
        return tasks

    def _refresh_tasks_tab(self):
        for w in self.tasks_inner.winfo_children(): w.destroy()
        date_str = self.tasks_date_var.get()
        filepath = CSV_DIR / f'{date_str}.csv'
        tasks = self._parse_csv(filepath)
        if not tasks:
            tk.Label(self.tasks_inner, text='📭 今天还没有待办计划\n对我说"今日待办"来生成一份吧~', font=FONT_SMALL, fg=self.T['muted'], bg=self.T['bg']).pack(pady=40)
            self.tasks_prog_label.config(text="0 / 0 已完成")
            return
        # 合并标签完成状态
        tags = {t['name']:{'td':t['today_done'],'ad':t['all_done'],'tp':t['target_pomodoros'] or 0,'id':t['id']} for t in self.db.all_tags() if t['tag_type']=='once'}
        done_count = 0
        for t in tasks:
            ti = tags.get(t['name'])
            if ti and ti['tp']>0:
                t['done'] = ti['td']>=ti['tp']
                t['donePomodoros'] = ti['td']
                t['tagId'] = ti['id']
            if t['done']: done_count+=1

        # 进度
        pct = round(done_count/len(tasks)*100) if tasks else 0
        self.tasks_prog_canvas.delete("all")
        w_prog = self.tasks_prog_canvas.winfo_width() or 400
        self.tasks_prog_canvas.create_rectangle(0,0,w_prog,8,fill=self.T['ring_bg'],outline="")
        if pct>0: self.tasks_prog_canvas.create_rectangle(0,0,w_prog*pct/100,8,fill=self.T['green'],outline="")
        self.tasks_prog_label.config(text=f"{done_count} / {len(tasks)} 已完成")

        # 分组
        groups = {'🔴High':[],'🟡Medium':[],'🟢Low':[]}
        for t in tasks: groups.get(t['priority'], groups['🟡Medium']).append(t)
        for pri,icon in [('🔴High','🔥'),('🟡Medium','📌'),('🟢Low','✅')]:
            g = groups[pri]
            if not g: continue
            tk.Label(self.tasks_inner, text=f"{icon} {pri.replace('🔴','').replace('🟡','').replace('🟢','')}  {len(g)}项", font=FONT_SMALL, fg=self.T['sub'], bg=self.T['bg'], anchor='w').pack(fill=tk.X, pady=(8,2))
            for t in g:
                card = tk.Frame(self.tasks_inner, bg=self.T['card'], bd=0, highlightthickness=0)
                card.pack(fill=tk.X, pady=2, ipady=6)
                # 左边色条
                border_color = {'🔴High':self.T['accent'],'🟡Medium':self.T['orange'],'🟢Low':self.T['green']}.get(pri,self.T['border'])
                tk.Frame(card, bg=border_color, width=4).pack(side=tk.LEFT, fill=tk.Y)
                # 内容
                body = tk.Frame(card, bg=self.T['card'])
                body.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=4)
                name_lbl = tk.Label(body, text=t['name'], font=FONT_LABEL, fg=self.T['muted'] if t['done'] else self.T['text'], bg=self.T['card'], anchor='w')
                name_lbl.pack(fill=tk.X)
                if t['done']: name_lbl.config(font=(FONT_LABEL[0],FONT_LABEL[1],'overstrike'))
                tk.Label(body, text=f"{t['domain']} · {t['estTime']}", font=FONT_SMALL, fg=self.T['muted'], bg=self.T['card'], anchor='w').pack(fill=tk.X)
                # 右侧
                meta = tk.Frame(card, bg=self.T['card'])
                meta.pack(side=tk.RIGHT, padx=10)
                if t['pomodoroCount']>0:
                    if self.active_task_index==t['index'] and self.running:
                        tk.Label(meta, text=f"⏱ {self.time_left//60:02d}:{self.time_left%60:02d}", font=FONT_BUTTON, fg=self.T['accent'], bg=self.T['card']).pack(side=tk.LEFT, padx=4)
                    else:
                        tk.Label(meta, text=f"🍅 {t['donePomodoros']}/{t['pomodoroCount']}" if not t['done'] else "🍅 ✓", font=FONT_SMALL, fg=self.T['text'], bg=self.T['card']).pack(side=tk.LEFT, padx=4)
                if not t['done']:
                    idx = t['index']
                    tk.Button(meta, text="▶", font=FONT_SMALL, bg=self.T['accent'], fg='white', relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=lambda i=idx: self._start_task(i)).pack(side=tk.LEFT)
                else:
                    tk.Label(meta, text="✓", font=FONT_BUTTON, fg=self.T['green'], bg=self.T['card']).pack(side=tk.LEFT, padx=4)
        self.tasks_inner.update_idletasks()
        self.tasks_canvas_w.configure(scrollregion=self.tasks_canvas_w.bbox("all"))

    def _start_task(self, task_index):
        date_str = self.tasks_date_var.get()
        filepath = CSV_DIR / f'{date_str}.csv'
        tasks = self._parse_csv(filepath)
        task = next((t for t in tasks if t['index']==task_index), None)
        if not task: return
        self._start_task_by_name(task['name'], task['pomodoroCount'])

    def _start_task_by_name(self, name, pomo_count=0):
        # 保存旧进度
        if self.running and self.session_start:
            elapsed = self.total_time-self.time_left
            if elapsed>=300:
                self.db.create_record(datetime.date.today().isoformat(), self.session_start, round(elapsed/60), 'completed', self.selected_tag['name'] if self.selected_tag else '')
            self.running = False
            if self.tick_after: self.root.after_cancel(self.tick_after); self.tick_after=None
            self.session_start = None
        # 重置
        self.mode = 'work'
        self.time_left = WORK_TIME
        self.total_time = WORK_TIME
        self.running = False
        # 查找或创建标签
        tags = self.db.all_tags()
        tag = next((t for t in tags if t['name']==name), None)
        if not tag:
            tid = self.db.create_tag(name, PRESET_COLORS[hash(name)%8], '', pomo_count if pomo_count>0 else None, 'once')
            tag = next((t for t in self.db.all_tags() if t['id']==tid), None)
        if tag:
            self.selected_tag = {'id':tag['id'],'name':tag['name'],'color':tag['color'],'icon':tag.get('icon','')}
            self.db.set_setting('last_tag', tag['name'])
        self._update_display()
        self.notebook.select(0)  # 切到计时页
        self._start()

    # ══════════════ 📊 看板页 ══════════════
    def _build_dashboard(self):
        f = self.dash_frame
        # 顶部按钮
        top = tk.Frame(f, bg=self.T['bg'])
        top.pack(fill=tk.X, padx=12, pady=(10,0))
        self.dash_view = tk.StringVar(value='heatmap')
        for v,txt in [('heatmap','🗓 热力图'),('trend','📈 趋势'),('cards','📋 统计')]:
            tk.Button(top, text=txt, font=FONT_SMALL, command=lambda v=v: self._show_dash_panel(v), bg=self.T['card'], fg=self.T['text'], borderwidth=0, cursor="hand2", padx=10).pack(side=tk.LEFT, padx=2)

        # 热力图面板
        self.dash_hm = tk.Frame(f, bg=self.T['bg'])
        self.dash_hm.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        self.dash_canvas = tk.Canvas(self.dash_hm, bg=self.T['card'], highlightthickness=0)
        self.dash_canvas.pack(fill=tk.BOTH, expand=True)

        # 趋势图面板
        self.dash_trend = tk.Frame(f, bg=self.T['bg'])
        self.dash_canvas_t = tk.Canvas(self.dash_trend, bg=self.T['card'], height=260, highlightthickness=0)
        self.dash_canvas_t.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        # 统计卡片面板
        self.dash_cards = tk.Frame(f, bg=self.T['bg'])
        self.dash_cards.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        self._build_stats_cards()

        self._show_dash_panel('heatmap')

    def _show_dash_panel(self, panel):
        self.dash_view.set(panel)
        self.dash_hm.pack_forget()
        self.dash_trend.pack_forget()
        self.dash_cards.pack_forget()
        if panel=='heatmap':
            self.dash_hm.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
            self._draw_heatmap()
        elif panel=='trend':
            self.dash_trend.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
            self._draw_trend()
        else:
            self.dash_cards.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
            self._refresh_stats()

    def _draw_heatmap(self):
        c = self.dash_canvas
        c.delete("all")
        data, fd, td = self.db.heatmap_data('year')
        year = datetime.date.today().year
        cell_size = 10; gap = 2; x0 = 40; y0 = 30
        # 简单年视图
        start = datetime.date(year,1,1)
        end = datetime.date(year,12,31)
        cur = start
        week_cols = {}
        while cur<=end:
            dow = cur.weekday()
            week_num = cur.isocalendar()[1]
            if week_num not in week_cols: week_cols[week_num] = [None]*7
            entry = data.get(cur.isoformat(),{'minutes':0})
            level = 0
            m = entry.get('minutes',0)
            if m>=120: level=4
            elif m>=60: level=3
            elif m>=25: level=2
            elif m>0: level=1
            colors_hm = [self.T['ring_bg'],'#9BE9A8','#40C463','#30A14E','#216E39']
            week_cols[week_num][dow] = {'date':cur.isoformat(),'level':level,'minutes':m}
            cur+=datetime.timedelta(days=1)
        sorted_weeks = sorted(week_cols.items())
        # 简单渲染
        for wi,(wn,days) in enumerate(sorted_weeks):
            for di,day in enumerate(days):
                if day is None: continue
                x = x0+wi*(cell_size+gap)
                y = y0+di*(cell_size+gap)
                color = colors_hm[day['level']] if day else self.T['ring_bg']
                c.create_rectangle(x,y,x+cell_size,y+cell_size,fill=color,outline="",tags="cell")
        c.create_text(x0+len(sorted_weeks)*7, y0+40, text=f"{year}年", font=FONT_SMALL, fill=self.T['sub'])

    def _draw_trend(self):
        c = self.dash_canvas_t
        c.delete("all")
        data = self.db.trend_data(90)
        if not data: return
        W = c.winfo_width() or 450; H = 260
        mx = max(5, max(d['minutes'] for d in data))
        margin = {'l':50,'r':15,'t':20,'b':40}
        pw, ph = W-margin['l']-margin['r'], H-margin['t']-margin['b']
        # 网格
        for i in range(5):
            y = margin['t']+ph*(1-i/4)
            c.create_line(margin['l'],y,W-margin['r'],y,fill=self.T['border'])
            c.create_text(margin['l']-10,y,text=f"{mx*i/4/60:.1f}h",font=FONT_SMALL,fill=self.T['muted'],anchor='e')
        # 数据线
        pts = []
        for i,d in enumerate(data):
            x = margin['l']+pw*i/max(1,len(data)-1)
            y = margin['t']+ph*(1-d['minutes']/mx)
            pts.extend([x,y])
        if len(pts)>=4:
            for i in range(0,len(pts)-2,2):
                c.create_line(pts[i],pts[i+1],pts[i+2],pts[i+3],fill=self.T['accent'],width=2)
            # 数据点
            for i in range(0,len(pts),2):
                c.create_oval(pts[i]-2,pts[i+1]-2,pts[i]+2,pts[i+1]+2,fill=self.T['accent'],outline="")
        # 目标线
        goal_m = int(self.settings.get('daily_goal_minutes',120))
        gy = margin['t']+ph*(1-goal_m/mx)
        c.create_line(margin['l'],gy,W-margin['r'],gy,fill=self.T['orange'],dash=(6,4))

    def _build_stats_cards(self):
        for w in self.dash_cards.winfo_children(): w.destroy()
        s = self.db.summary()
        cards_data = [
            ("📅", self._fmt_min(s['today']['total_minutes']), "今日专注", f"{s['today']['pomodoro_count']}个番茄"),
            ("📆", self._fmt_min(s['week']['total_minutes']), "本周总时长", ""),
            ("📊", self._fmt_min(s['month']['total_minutes']), "本月总时长", ""),
            ("🔥", f"{s['streak']}天", "连续专注", ""),
            ("🏆", self._fmt_min(s['total']), "累计总时长", ""),
            ("🏷", " / ".join(t['tag'] for t in s.get('top_tags',[])) or "—", "TOP3标签", ""),
        ]
        for i,(icon,val,label,_) in enumerate(cards_data):
            card = self._fbg(self.dash_cards)
            card.place(relx=(i%3)*0.33+0.02, rely=(i//3)*0.33+0.02, relwidth=0.3, relheight=0.3)

    def _refresh_stats(self):
        self._build_stats_cards()

    def _refresh_dashboard(self):
        if self.dash_view.get()=='heatmap': self._draw_heatmap()
        elif self.dash_view.get()=='trend': self._draw_trend()
        else: self._refresh_stats()

    def _fmt_min(self, m):
        if m<60: return f"{m}m"
        return f"{m//60}h{m%60}m"

    # ══════════════ 🎯 目标页 ══════════════
    def _build_goals(self):
        f = self.goals_frame
        self.goals_canvas_w = tk.Canvas(f, bg=self.T['bg'], highlightthickness=0)
        scrollbar = tk.Scrollbar(f, orient=tk.VERTICAL, command=self.goals_canvas_w.yview)
        self.goals_inner = tk.Frame(self.goals_canvas_w, bg=self.T['bg'])
        self.goals_inner.bind("<Configure>", lambda e: self.goals_canvas_w.configure(scrollregion=self.goals_canvas_w.bbox("all")))
        self.goals_canvas_w.create_window((0,0), window=self.goals_inner, anchor="nw")
        self.goals_canvas_w.configure(yscrollcommand=scrollbar.set)
        self.goals_canvas_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=6)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._refresh_goals_tab()

    def _refresh_goals_tab(self):
        for w in self.goals_inner.winfo_children(): w.destroy()
        goals = self.db.get_goals_progress()
        total_done = sum(g['donePomo'] for g in goals)
        total_est = sum(g['totalPomo'] for g in goals)
        pct = round(total_done/total_est*100) if total_est>0 else 0
        tk.Label(self.goals_inner, text=f"🚀 总体进度：{total_done} / {total_est} 番茄 ({pct}%)", font=FONT_LABEL, fg=self.T['sub'], bg=self.T['bg']).pack(pady=(10,8))
        for g in goals:
            card = self._fbg(self.goals_inner)
            card.pack(fill=tk.X, pady=4, ipady=6)
            tk.Frame(card, bg=g['color'], width=4).pack(side=tk.LEFT, fill=tk.Y)
            hdr = tk.Frame(card, bg=self.T['card'])
            hdr.pack(fill=tk.X, padx=10, pady=(6,2))
            tk.Label(hdr, text=f"{g['icon']} {g['name']}", font=FONT_LABEL, fg=self.T['text'], bg=self.T['card']).pack(side=tk.LEFT)
            pct_color = '#27AE60' if g['pct']>=60 else ('#E67E22' if g['pct']>=30 else '#E74C3C')
            tk.Label(hdr, text=f"{g['pct']}%", font=FONT_BUTTON, fg=pct_color, bg=self.T['card']).pack(side=tk.RIGHT)
            bar = tk.Canvas(card, height=8, bg=self.T['card'], highlightthickness=0)
            bar.pack(fill=tk.X, padx=10, pady=(0,2))
            w_bar = card.winfo_width() or 400
            bar.create_rectangle(0,0,w_bar,8,fill=self.T['ring_bg'],outline="")
            if g['pct']>0: bar.create_rectangle(0,0,w_bar*g['pct']/100,8,fill=g['color'],outline="")
            tk.Label(card, text=f"已完成 {g['donePomo']} 番茄  |  目标 {g['totalPomo']} 番茄", font=FONT_SMALL, fg=self.T['muted'], bg=self.T['card']).pack(anchor='w', padx=10, pady=(0,6))

    # ══════════════ ⚙ 设置页 ══════════════
    def _build_settings(self):
        f = self.settings_frame
        # 计时设置
        c1 = self._fbg(f)
        c1.pack(fill=tk.X, padx=12, pady=(10,4), ipady=8)
        tk.Label(c1, text="⏱ 计时设置", font=FONT_LABEL, fg=self.T['text'], bg=self.T['card']).pack(anchor='w', padx=10, pady=(6,2))
        for label,key,vals in [("专注时长(分)","work_duration",(1,120)),("短休(分)","short_break_duration",(1,30)),("长休(分)","long_break_duration",(1,60)),("长休间隔","pomodoros_before_long",(1,10))]:
            row = tk.Frame(c1, bg=self.T['card'])
            row.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, fg=self.T['sub'], bg=self.T['card']).pack(side=tk.LEFT)
            sv = tk.StringVar(value=self.db.get_setting(key) or '25')
            tk.Spinbox(row, from_=vals[0], to=vals[1], width=6, textvariable=sv, font=FONT_SMALL).pack(side=tk.RIGHT)
            setattr(self, f'set_{key}', sv)
        # 每日目标
        tk.Label(c1, text="每日目标(小时)", font=FONT_SMALL, fg=self.T['sub'], bg=self.T['card']).pack(anchor='w', padx=10)
        sv_goal = tk.StringVar(value=str(int(self.settings.get('daily_goal_minutes',120))/60))
        tk.Spinbox(c1, from_=0.5, to=24, increment=0.5, width=6, textvariable=sv_goal, font=FONT_SMALL).pack(anchor='w', padx=10)
        setattr(self,'set_daily_goal',sv_goal)
        # 主题
        c2 = self._fbg(f)
        c2.pack(fill=tk.X, padx=12, pady=4, ipady=8)
        tk.Label(c2, text="🌓 主题", font=FONT_LABEL, fg=self.T['text'], bg=self.T['card']).pack(anchor='w', padx=10, pady=(6,2))
        tk.Button(c2, text="☀️ 浅色" if self.theme_name=='dark' else "🌙 深色", font=FONT_BUTTON, bg=self.T['card'], fg=self.T['text'], command=self._toggle_theme).pack(anchor='w', padx=10, pady=4)
        # 保存按钮
        tk.Button(f, text="💾 保存设置", font=FONT_BUTTON, bg=self.T['accent'], fg='white', relief=tk.FLAT, padx=20, pady=8, cursor="hand2", command=self._save_settings).pack(pady=12)
        # 数据管理
        c3 = self._fbg(f)
        c3.pack(fill=tk.X, padx=12, pady=4, ipady=8)
        tk.Label(c3, text="📤 数据管理", font=FONT_LABEL, fg=self.T['text'], bg=self.T['card']).pack(anchor='w', padx=10, pady=(6,2))
        tk.Label(c3, text=f"数据库: {DB_PATH}", font=FONT_SMALL, fg=self.T['muted'], bg=self.T['card']).pack(anchor='w', padx=10)
        bf = tk.Frame(c3, bg=self.T['card'])
        bf.pack(fill=tk.X, padx=10, pady=4)
        tk.Button(bf, text="导出 JSON", font=FONT_SMALL, command=self._export_json, bg=self.T['card'], fg=self.T['text']).pack(side=tk.LEFT, padx=2)
        tk.Button(bf, text="导出 CSV", font=FONT_SMALL, command=self._export_csv, bg=self.T['card'], fg=self.T['text']).pack(side=tk.LEFT, padx=2)
        tk.Button(bf, text="📦 备份", font=FONT_SMALL, command=self._backup_db, bg=self.T['card'], fg=self.T['text']).pack(side=tk.LEFT, padx=2)

    def _toggle_theme(self):
        self.theme_name = 'dark' if self.theme_name=='light' else 'light'
        self.db.set_setting('theme', self.theme_name)
        self._apply_theme()

    def _save_settings(self):
        for key in ['work_duration','short_break_duration','long_break_duration','pomodoros_before_long']:
            sv = getattr(self,f'set_{key}',None)
            if sv: self.db.set_setting(key, sv.get())
        svg = getattr(self,'set_daily_goal',None)
        if svg:
            try: self.db.set_setting('daily_goal_minutes', str(int(float(svg.get())*60)))
            except: pass
        self.settings = self.db.get_all_settings()
        messagebox.showinfo("保存","设置已保存！")

    def _export_json(self):
        data = self.db.export_json()
        path = filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if path:
            with open(path,'w',encoding='utf-8') as f: f.write(data)
            messagebox.showinfo("导出","导出完成!")

    def _export_csv(self):
        data = self.db.export_csv()
        path = filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if path:
            with open(path,'w',encoding='utf-8',newline='') as f: f.write(data)
            messagebox.showinfo("导出","导出完成!")

    def _backup_db(self):
        data = self.db.backup()
        path = filedialog.asksaveasfilename(defaultextension=".zip",filetypes=[("ZIP","*.zip")])
        if path:
            with open(path,'wb') as f: f.write(data)
            messagebox.showinfo("备份","备份完成!")

    # ══════════════ 系统托盘 ══════════════
    def _setup_tray(self):
        try:
            from PIL import Image
            import pystray
            icon_file = BASE_DIR/'static'/'icon.png'
            if icon_file.exists():
                img = Image.open(icon_file).resize((32,32),Image.LANCZOS)
            else:
                img = Image.new('RGBA',(32,32),(0,0,0,0))
            menu = pystray.Menu(pystray.MenuItem('打开番茄钟',self._show_from_tray,default=True),pystray.Menu.SEPARATOR,pystray.MenuItem('退出',self._quit_app))
            self.tray_icon = pystray.Icon('pomodoro',img,'番茄钟',menu)
            threading.Thread(target=self.tray_icon.run,daemon=True).start()
        except: self.tray_icon = None

    def _show_from_tray(self):
        self.root.after(0, lambda: [self.root.deiconify(), self.root.lift()])

    def _on_close(self):
        if self.running and self.session_start:
            if messagebox.askyesno("计时中","计时器正在运行，确定退出吗？"):
                self._stop_timer()
                self._quit_app()
        else:
            self._quit_app()

    def _quit_app(self):
        if self.tray_icon:
            try: self.tray_icon.stop()
            except: pass
        self.root.destroy()
        os._exit(0)

    def minimize_to_tray(self):
        self.root.withdraw()

    def run(self):
        self._setup_tray()
        self.root.mainloop()


if __name__ == "__main__":
    app = PomodoroApp()
    app.run()

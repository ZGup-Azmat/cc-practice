# 番茄钟 v4 — 架构总览与功能清单

> 📅 生成日期：2026-06-15 | 版本：v4.x

## 项目背景

本地番茄钟桌面应用，基于 Flask + SQLite + pywebview 打包。

| 项目 | 路径/值 |
|------|---------|
| 源码目录 | `C:\Users\BHkx\Desktop\first-cc\` |
| 打包产物 | `dist/Pomodoro.exe` |
| 数据文件 | `dist/pomodoro.db`（与 .exe 同目录） |
| 启动方式 | 双击 exe / `python app.py --browser` / `python app.py` |
| 浏览器地址 | `http://127.0.0.1:5678` |
| GitHub | `github.com/ZGup-Azmat/cc-practice` |

---

## 一、技术架构

```
first-cc/
├── app.py                  # Flask 后端 (REST API + SQLite + pywebview + 系统托盘)
├── pomodoro.py             # v1 Tkinter 原型（保留参考）
├── requirements.txt        # 依赖：flask, pystray, Pillow, pywebview, pyinstaller
├── Pomodoro.spec           # PyInstaller 打包配置
├── static/
│   ├── index.html          # 单页应用 (4 个 Tab)
│   ├── style.css           # 双主题样式 (浅色 + 深色)
│   ├── app.js              # 原生 JS (~2100 行，无框架)
│   ├── mini.html / mini.css # 迷你悬浮窗
│   ├── icon.png / tomato.ico # 应用图标
├── dist/
│   ├── Pomodoro.exe        # 打包好的桌面应用
│   └── pomodoro.db         # 运行时数据库
├── update/                 # 版本升级说明
├── electron/               # Electron 备用打包方案
└── issue/                  # 用户反馈 Issue 记录
```

### 后端 `app.py` (Flask)

- **数据库**：SQLite，单文件 `pomodoro.db`，3 张表
  - `settings` — 键值对配置
  - `pomodoro_records` — 番茄记录（按 date + tag 索引）
  - `tags` — 标签管理（id, name, color, icon, target_pomodoros, tag_type）
- **运行模式**：
  - `python app.py` → pywebview 原生桌面窗口（无边框 + 自定义标题栏）
  - `python app.py --browser` → 浏览器模式 + 系统托盘
  - `python app.py --headless` → 纯后端（供 Electron 加载）
- **关键 API** (20+ 端点)

### 前端 `static/` (原生 JS)

- 零框架，纯 HTML + CSS + JS
- 计时器采用墙钟时间戳 (`Date.now()`) 防止后台节流
- `STATE` 对象集中管理全部前端状态
- 4 个视图 Tab，CSS class 切换
- 深色/浅色双主题（CSS 变量）
- 30 秒轮询自动刷新看板/目标数据

---

## 二、功能清单

### ⏱ 计时页（Timer）

| 功能 | 说明 |
|------|------|
| 番茄钟循环 | 专注 25min → 短休 5min → 专注 25min → … → 4 个后长休 15min（可配置） |
| SVG 圆环进度 | 实时绘制圆弧剩余比例 |
| 当前任务显示 | 从任务页启动后，钟表上直接显示任务名 |
| 开始/暂停/停止/跳过 | 4 个控制按钮 |
| 停止 ≥5min 保留 | 专注满 5 分钟终止时保存为有效记录，不足则丢弃 |
| 墙钟计时 | 用 `Date.now()` 防浏览器后台节流 |
| 番茄完成通知 | 声音 + 浏览器 Notification |
| 反思弹窗 | 番茄完成后可选填：专注度评分 (1-5★) + 简短反思 |
| 每日目标进度条 | 实时显示今日专注时长/目标百分比，达成撒花 🎉 |
| 自定义标题栏 | 最小化/关闭（计时中关闭弹窗询问：保存并退出 / 最小化到悬浮窗） |
| 启动画面 | 随机励志语录，1.8 秒渐隐 |

### 📊 看板页（Dashboard）

| 功能 | 说明 |
|------|------|
| 🗓 热力图 | GitHub 风格，年/月视图，颜色深浅表示专注时长 |
| 热力图 Tooltip | 悬停显示当日总时长 + 按标签明细（含已删除标签灰色 fallback） |
| 标签筛选联动 | 热力图 + 趋势图可按标签过滤 |
| 📈 趋势折线图 | Canvas 绘制，日/周/月粒度，目标虚线标注 |
| 📋 统计卡片 | 今日/本周/本月/连续天数/累计总时长/TOP3 标签 |
| 📂 标签明细 | 时间段筛选（全部/本周/本月/今日），进度条 + 7 日迷你柱状图 |

### 📋 任务页（Tasks）★ v4 新增

| 功能 | 说明 |
|------|------|
| CSV 导入 | 自动读取 `每日待办/YYYY-MM-DD.csv`，Claude 生成后即现 |
| 日期切换 | ◀ ▶ 箭头翻看历史/未来待办 |
| 优先级分组 | 🔴高 / 🟡中 / 🟢低 三组，左边框颜色区分 |
| 预估番茄数 | 每个任务显示 🍅 x/y（待完成/总数） |
| ▶ 一键开始 | 点击任务右侧 ▶ → 自动创建标签 → 跳计时页 → 自动开始倒计时 |
| 实时倒计时 | 进行中的任务卡片 🍅 徽章变为 ⏱ MM:SS 每秒更新 |
| 计时中切任务 | 旧进度 ≥5min 自动保存，新任务无缝启动 |
| 完成状态 | 全部番茄完成 → 卡片变灰 + 打勾 ✓ |
| ＋ 快速添加 | 展开面板：填名称 + 选类型 + 定番茄数 → 创建并开始 |
| 任务类型 | 一次性 (once) / 每日习惯 (daily) / 长期项目 (long) |

### 🎯 目标页（Goals）★ v4 新增

| 功能 | 说明 |
|------|------|
| 9 大目标卡片 | GPA / 雅思 / GitHub / GRE / 科研 / LeetCode / 体脂 / 德语 / 阅读 |
| 进度条 | 每个目标显示已完成番茄 / 预估总番茄 + 百分比 |
| 自动追踪 | 标签关键词匹配 → 完成番茄自动累加对应目标进度 |
| 总体进度 | 顶部汇总：总计已完成/总预估番茄 |
| 单次 SQL 聚合 | 所有目标一次查询完成（非 N+1） |

### ⚙ 设置页（Settings）

| 功能 | 说明 |
|------|------|
| 计时配置 | 专注时长 / 短休 / 长休 / 长休间隔 |
| 每日目标 | 可调小时数 |
| 主题切换 | 浅色 / 深色 |
| 数据管理 | 查看数据库路径 / 复制路径 / 打开文件夹 |
| 数据导出 | JSON / CSV |
| 完整备份 | 下载 pomodoro.db 的 zip |

---

## 三、关键设计决策

| 决策 | 原因 |
|------|------|
| 原生 JS 无框架 | 零构建步骤，PyInstaller 直接打包 |
| SQLite 单文件 | 数据与 exe 同目录，纯本地零网络 |
| CSV 只读不写 | Claude 生成的计划不被污染，完成状态存 tags 表 |
| 任务→标签自动创建 | 点 ▶ 时自动创建 `tag_type='once'` 的临时标签 |
| 目标关键词匹配 | 标签名 LIKE 匹配 → 进度自动累积（9 个目标 ~50 关键词） |
| 墙钟计时 | `Date.now()` 防 Chrome 后台 setInterval 节流 |
| 无外部 CDN | 所有资源本地打包，完全离线可用 |

---

## 四、版本演进

| 版本 | 日期 | 主要内容 |
|------|------|---------|
| v1 | - | Tkinter 原型 (`pomodoro.py`) |
| v2 | - | Flask + SQLite + pywebview + 看板 |
| v3 | 2026-06 | 标签选择器 / 标签 CRUD / 热力图 tooltip 升级 / 数据管理 |
| v3.1 | 2026-06 | 标签目标番茄数 + 每日/一次性模式 |
| v3.2 | 2026-06-14 | 墙钟计时 / 窗口缩放 / 关闭行为 / 启动画面 / 悬浮窗 |
| v4 | 2026-06-15 | 📋 任务页 (CSV导入+▶启动+实时倒计时) / 🎯 目标页 (9大目标追踪) / 计时页简化 |

---

## 五、数据库 Schema

```sql
-- 配置表
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- 番茄记录
CREATE TABLE pomodoro_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('completed','abandoned')),
    tag TEXT DEFAULT '',
    focus_score INTEGER DEFAULT NULL,
    reflection TEXT DEFAULT ''
);
CREATE INDEX idx_date ON pomodoro_records(date);
CREATE INDEX idx_tag ON pomodoro_records(tag);

-- 标签/项目管理
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#27AE60',
    icon TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    target_pomodoros INTEGER DEFAULT NULL,
    tag_type TEXT DEFAULT 'daily'  -- 'daily' | 'once' | 'long'
);
```

## 六、API 端点汇总

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/settings` | 获取设置 |
| PUT | `/api/settings` | 更新设置 |
| GET | `/api/records` | 查询番茄记录 |
| POST | `/api/records` | 创建番茄记录 |
| GET | `/api/stats/today` | 今日统计 |
| GET | `/api/stats/summary` | 完整摘要 |
| GET | `/api/stats/by-tag` | 按标签统计 |
| GET | `/api/stats/heatmap` | 热力图数据 |
| GET | `/api/stats/trend` | 趋势数据 |
| GET | `/api/stats/day-detail` | 单日标签明细 |
| GET | `/api/tags` | 标签列表 |
| POST | `/api/tags` | 创建标签 |
| PUT | `/api/tags/<id>` | 更新标签 |
| DELETE | `/api/tags/<id>` | 删除标签 |
| GET/PUT | `/api/timer-state` | 迷你窗计时状态同步 |
| GET | `/api/daily-tasks` | 读取每日任务 CSV |
| POST | `/api/daily-tasks/toggle` | 切换任务完成 |
| GET | `/api/daily-tasks/history` | 任务日期列表 |
| GET | `/api/goals` | 目标体系 + 进度 |
| GET | `/api/export` | 导出数据 |
| GET | `/api/backup` | 下载备份 |
| POST | `/api/open-data-folder` | 打开数据目录 |
| GET | `/api/data-path` | 数据库路径 |

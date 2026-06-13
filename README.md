# 🍅 番茄钟 Pomodoro Timer

A local-first Pomodoro timer desktop app with data visualization dashboard, tag management, and system tray integration.

**本地优先的番茄钟桌面应用**，内置数据看板、标签管理和系统托盘。

## 📖 About 关于

A minimalist Pomodoro timer built for focused work sessions. Track your time with visual tags, review productivity patterns through heatmaps and trend charts, and manage everything offline — your data stays in a single SQLite file next to the executable. The app runs as a native Windows desktop window (via pywebview) or in the browser for development.

**极简番茄钟**，为专注工作而生。用可视化标签追踪时间，通过热力图和趋势图表回顾效率模式。一切离线运行，数据存储在与可执行文件同目录的 SQLite 文件中。支持原生 Windows 桌面窗口和浏览器开发模式。

---

## ✨ Features 功能

- ⏱ **Pomodoro Timer** — 25/5/15 minute work-break cycles with circular progress ring
- 🏷 **Visual Tag Selector** — 8 preset colors + emoji, click to select / double-click to start, locks during focus
- 📊 **Dashboard** — GitHub-style heatmap, Canvas trend chart, stats cards
- 🏷 **Tag Breakdown** — time-filtered stats with proportional progress bars + 7-day mini bar charts
- 🔗 **Tag → Heatmap Linking** — click any tag row to filter the heatmap
- ⚙ **Settings** — timers, daily goal, tag management (CRUD), data management (export/backup/path)
- 🌓 **Dark / Light Theme**
- 🎉 **Confetti** — daily goal celebration
- 🖥 **Native Desktop Window** — via pywebview, or browser dev mode
- 📦 **Fully Offline** — zero external requests, self-contained

---

## 🚀 Quick Start 快速开始

```bash
# Install dependencies
pip install -r requirements.txt

# Dev mode — opens in browser with system tray
python app.py --browser

# Desktop mode — native pywebview window
python app.py

# Package to .exe
pyinstaller Pomodoro.spec
```

The app serves at **`http://127.0.0.1:5678`**. Database is created at `pomodoro.db` next to the executable.

---

## 🏗 Architecture 架构

```
first-cc/
├── app.py              # Flask backend (REST API + SQLite + tray)
├── static/
│   ├── index.html      # Single-page app (timer / dashboard / settings)
│   ├── style.css       # Dual-theme styles (light + dark)
│   └── app.js          # Vanilla JS (state machine, charts, tag selector)
├── dist/
│   └── Pomodoro.exe    # Packaged executable (pyinstaller)
├── Update/             # Version upgrade specs
├── requirements.txt
├── Pomodoro.spec       # PyInstaller build config
└── pomodoro.db         # SQLite database (auto-created)
```

**Backend** — Flask + sqlite3 (no ORM). Two run modes: `--browser` (tray icon + browser) and default (pywebview native window).

**Frontend** — Vanilla JS single-page app, no frameworks. Three views: Timer, Dashboard (heatmap / trend / cards), Settings.

**Database** — Single SQLite file with tables: `settings`, `pomodoro_records`, `tags`.

---

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Get all settings |
| PUT | `/api/settings` | Update settings |
| GET | `/api/records` | Query pomodoro records |
| POST | `/api/records` | Create a pomodoro record |
| GET | `/api/stats/today` | Today's stats |
| GET | `/api/stats/summary` | Full summary (today/week/month/streak/total) |
| GET | `/api/stats/by-tag` | Breakdown by tag (supports `?period=`) |
| GET | `/api/stats/heatmap` | Heatmap data (`?view=year|month`) |
| GET | `/api/stats/trend` | Trend chart data |
| GET | `/api/stats/day-detail` | Single-day tag breakdown (with ghost tag fallback) |
| GET | `/api/tags` | List all tags |
| POST | `/api/tags` | Create a tag |
| PUT | `/api/tags/<id>` | Update a tag |
| DELETE | `/api/tags/<id>` | Delete a tag (preserves history) |
| GET | `/api/export` | Export records (`?format=csv|json`) |
| GET | `/api/backup` | Download zipped database |
| POST | `/api/open-data-folder` | Open data directory |
| GET | `/api/data-path` | Get database file path |

---

## 🔄 Data Migration 数据迁移

Old `pomodoro.db` files auto-migrate on first launch:
- Existing distinct tag names in `pomodoro_records` are imported into the new `tags` table
- Deleted tags preserve historical records — they display with a gray fallback color (`#94A3B8`)
- All old data is retained intact

---

## 🎨 Design Language 设计语言

| Token | Value |
|-------|-------|
| Accent (Tomato Red) | `#E74C3C` |
| Success (Mint Green) | `#27AE60` |
| Card Background | `#F5F7FA` |
| Text Primary | `#2C3E50` |
| Ghost Tag Fallback | `#94A3B8` |
| Preset Colors | Red / Orange / Yellow / Green / Cyan / Blue / Purple / Pink |

---

## 📋 Version History 版本历史

| Version | Highlights |
|---------|-----------|
| **v3** | Visual tag selector, tag CRUD, enhanced heatmap tooltip, stats card linking, mini bar charts, data management, Access ODBC guide |
| **v2** | Flask + SQLite backend, pywebview desktop packaging, system tray, dashboard with heatmap/trend/cards |
| **v1** | Tkinter prototype (kept for reference as `pomodoro.py`) |

---

## 🔧 Tech Stack 技术栈

- **Backend**: Python + Flask + sqlite3
- **Frontend**: Vanilla JS + CSS (no frameworks, no bundlers)
- **Desktop**: pywebview (Windows native window)
- **Packaging**: PyInstaller
- **Offline**: Zero external dependencies at runtime

---

## 📄 License

MIT

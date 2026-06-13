# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A local-first Pomodoro timer desktop app with data visualization dashboard. Two generations exist:
- `pomodoro.py` — v1 tkinter prototype (no persistence, kept for reference).
- `app.py` + `static/` — v2 (active): Flask backend + web frontend + SQLite, packaged as a native Windows desktop app via pywebview.

## Run & build

```bash
# Install dependencies
pip install -r requirements.txt

# Dev mode — opens in browser with system tray icon
python app.py --browser

# Desktop mode — native pywebview window
python app.py

# Package to .exe (outputs to dist/Pomodoro.exe)
pyinstaller Pomodoro.spec
```

The app serves on `http://127.0.0.1:5678`. Database is created at `pomodoro.db` in the current directory (next to the .exe when packaged).

## Architecture

**Backend (`app.py`)** — Flask server with SQLite via raw sqlite3 (no ORM). Two run modes:
- `--browser` mode: opens the default web browser + system tray icon (pystray).
- Default desktop mode: creates a pywebview native window wrapping the Flask URL.

Database initialization runs lazily on the first request via `@app.before_request`. All data is local — zero network calls.

Key API routes:
- `GET/PUT /api/settings` — app settings (timers, daily goal, theme)
- `GET/POST /api/records` — pomodoro session records
- `GET /api/stats/today`, `/summary`, `/by-tag`, `/heatmap`, `/trend` — statistics
- `GET /api/export?format=csv|json` — data export

**Frontend (`static/`)** — Single-page vanilla JS app (no framework). Three views (timer → dashboard → settings) managed by CSS class toggling. Dashboard has three sub-panels: heatmap (GitHub-style), Canvas trend chart, stats cards.

State is held in `STATE` object in `app.js`. API calls go through the `API` module. A 30-second polling interval refreshes all visible dashboard panels and the daily goal bar.

**Database** — Single SQLite file (`pomodoro.db`) with two tables:
- `settings` — key/value pairs with defaults inserted on first run
- `pomodoro_records` — indexed on `date` and `tag`, status is `completed` or `abandoned`

**Packaging** — PyInstaller spec bundles `app.py` + `static/` into `dist/Pomodoro.exe`. Uses `sys.executable` parent as `BASE_DIR` when frozen to persist database next to the .exe.

## Important implementation notes

- `sys.frozen` check at app startup determines if running from PyInstaller .exe — `BASE_DIR` changes accordingly so the database survives app restarts.
- No iframes, no external CDN, no external fonts — everything is self-contained for offline use.
- The timer state lives entirely in the browser JS (`STATE` object). The backend is purely a REST API with no session management or server-side timer state.
- In `--browser` mode, the system tray is created with pystray and runs on the main thread (blocking). Flask runs on a daemon thread.
- When running in pywebview mode, `os._exit(0)` is used to force-quit after the window closes (Flask background thread won't shut down cleanly otherwise).

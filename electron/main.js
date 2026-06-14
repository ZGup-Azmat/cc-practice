// ═══════════════════════════════════════════════════════════
//  Electron 主进程 — 番茄钟桌面壳
//  无边框圆角窗口 · 自定义图标 · 关闭拦截 · 圆形悬浮窗 · 系统托盘
// ═══════════════════════════════════════════════════════════

const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  ipcMain,
  nativeImage,
  screen,
} = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

// ── 常量 ──────────────────────────────────────────────────
const FLASK_PORT = 5678;
const FLASK_URL = `http://127.0.0.1:${FLASK_PORT}`;

// ── 全局引用 ──────────────────────────────────────────────
let mainWindow = null;
let miniWindow = null;
let tray = null;
let flaskProcess = null;
let isQuitting = false;

// ── 路径 ──────────────────────────────────────────────────
const isDev = !app.isPackaged;
const rootDir = isDev ? path.join(__dirname, '..') : process.resourcesPath;
const staticDir = path.join(rootDir, 'static');
const iconPath = path.join(staticDir, 'icon.png');

// ── Flask 生命周期 ────────────────────────────────────────

function killFlask() {
  if (flaskProcess) {
    try { flaskProcess.kill(); } catch (_) { /* already dead */ }
    flaskProcess = null;
  }
}

function startFlask() {
  if (isDev) {
    flaskProcess = spawn('python', ['app.py', '--headless'], { cwd: rootDir });
  } else {
    const serverExe = path.join(process.resourcesPath, 'server', 'server.exe');
    flaskProcess = spawn(serverExe, ['--headless']);
  }

  flaskProcess.stdout.on('data', d => console.log(`[Flask] ${d.toString().trim()}`));
  flaskProcess.stderr.on('data', d => console.error(`[Flask] ${d.toString().trim()}`));
  flaskProcess.on('error', err => console.error('[Flask] Failed:', err.message));
}

function waitForFlask(retries = 40) {
  return new Promise((resolve, reject) => {
    function check(remaining) {
      http.get(`${FLASK_URL}/api/settings`, res => {
        res.destroy();
        resolve();
      }).on('error', () => {
        if (remaining <= 0) return reject(new Error('Flask 启动超时'));
        setTimeout(() => check(remaining - 1), 250);
      });
    }
    check(retries);
  });
}

// ── 主窗口 ────────────────────────────────────────────────

async function createMainWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: 500,
    height: 820,
    minWidth: 320,
    minHeight: 480,
    x: Math.round((sw - 500) / 2),
    y: Math.round((sh - 820) / 2),
    frame: false,              // 无边框 → 圆角由 CSS 控制
    transparent: true,         // 允许 CSS 圆角透过透明区域
    title: 'Tomato Timer',
    autoHideMenuBar: true,
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(FLASK_URL);

  // 原生关闭拦截（Alt+F4 / 任务栏关闭）
  mainWindow.on('close', e => {
    if (!isQuitting && mainWindow) {
      e.preventDefault();
      mainWindow.webContents.send('request-close');
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── 迷你悬浮窗 ────────────────────────────────────────────

function showMiniWindow() {
  if (miniWindow) {
    miniWindow.show();
    miniWindow.focus();
    return;
  }

  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;

  miniWindow = new BrowserWindow({
    width: 210,
    height: 240,
    x: sw - 230,
    y: sh - 260,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: true,
    title: 'Tomato Mini',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  miniWindow.loadURL(`${FLASK_URL}/mini`);

  miniWindow.on('closed', () => {
    miniWindow = null;
  });
}

function hideMiniWindow() {
  if (miniWindow) {
    miniWindow.close();
    miniWindow = null;
  }
}

// ── 系统托盘 ──────────────────────────────────────────────

function createTray() {
  try {
    const icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
    tray = new Tray(icon);

    const contextMenu = Menu.buildFromTemplate([
      {
        label: '显示番茄钟',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          }
        },
      },
      { type: 'separator' },
      {
        label: '退出',
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]);

    tray.setToolTip('🍅 番茄钟');
    tray.setContextMenu(contextMenu);

    // 双击托盘图标恢复窗口
    tray.on('double-click', () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
      }
    });
  } catch (err) {
    console.warn('[Tray] 托盘创建失败:', err.message);
  }
}

// ── IPC 处理 ──────────────────────────────────────────────

function setupIPC() {
  ipcMain.handle('minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.handle('close-app', () => {
    isQuitting = true;
    app.quit();
  });

  ipcMain.handle('show-mini', () => {
    showMiniWindow();
  });

  ipcMain.handle('hide-mini', () => {
    hideMiniWindow();
    // 恢复主窗口
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ── 应用生命周期 ──────────────────────────────────────────

app.whenReady().then(async () => {
  setupIPC();
  createTray();
  startFlask();

  try {
    await waitForFlask();
  } catch (e) {
    console.error(e.message);
    app.quit();
    return;
  }

  await createMainWindow();
});

app.on('window-all-closed', () => {
  // Windows 上不退出，保留托盘
  // macOS: if (process.platform !== 'darwin')
});

app.on('before-quit', () => {
  isQuitting = true;
  killFlask();
  hideMiniWindow();
});

app.on('activate', () => {
  // macOS: 点击 dock 图标恢复窗口
  if (mainWindow === null) {
    createMainWindow();
  } else {
    mainWindow.show();
  }
});

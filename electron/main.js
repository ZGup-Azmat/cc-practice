const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const FLASK_PORT = 5678;
const FLASK_URL = `http://127.0.0.1:${FLASK_PORT}`;

let flaskProcess = null;

function killFlask() {
  if (flaskProcess) {
    flaskProcess.kill();
    flaskProcess = null;
  }
}

function startFlask() {
  const isDev = !app.isPackaged;

  if (isDev) {
    const appDir = path.join(__dirname, '..');
    flaskProcess = spawn('python', ['app.py', '--headless'], { cwd: appDir });
  } else {
    const serverExe = path.join(process.resourcesPath, 'server', 'server.exe');
    flaskProcess = spawn(serverExe, ['--headless']);
  }

  flaskProcess.stdout.on('data', (data) => {
    console.log(`[Flask] ${data.toString().trim()}`);
  });
  flaskProcess.stderr.on('data', (data) => {
    console.error(`[Flask] ${data.toString().trim()}`);
  });
  flaskProcess.on('error', (err) => {
    console.error('[Flask] Failed to start:', err.message);
  });
}

function waitForFlask(retries = 30) {
  return new Promise((resolve, reject) => {
    function check(remaining) {
      http.get(FLASK_URL + '/api/settings', (res) => {
        res.destroy(); // 立即释放 socket，不消费 body
        resolve();
      }).on('error', () => {
        if (remaining <= 0) return reject(new Error('Flask 启动超时'));
        setTimeout(() => check(remaining - 1), 300);
      });
    }
    check(retries);
  });
}

async function createWindow() {
  startFlask();

  try {
    await waitForFlask();
  } catch (e) {
    console.error(e.message);
    app.quit();
    return;
  }

  const win = new BrowserWindow({
    width: 500,
    height: 800,
    minWidth: 420,
    minHeight: 640,
    title: 'Tomato Timer',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  win.loadURL(FLASK_URL);

  win.on('closed', killFlask);
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  killFlask();
  app.quit();
});

app.on('before-quit', killFlask);

// ═══════════════════════════════════════════════════════════
//  Electron Preload — 暴露 pywebview 兼容 API 给前端
//  前端无需改动，window.pywebview.api 调用自动转到 IPC
// ═══════════════════════════════════════════════════════════

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pywebview', {
  api: {
    minimize: () => ipcRenderer.invoke('minimize'),
    close_app: () => ipcRenderer.invoke('close-app'),
    show_mini: () => ipcRenderer.invoke('show-mini'),
    hide_mini: () => ipcRenderer.invoke('hide-mini'),
  },
});

// 监听主进程的关闭请求（Alt+F4 / 任务栏关闭）
ipcRenderer.on('request-close', () => {
  // 触发自定义关闭按钮逻辑，复用 app.js 中的处理
  const btnClose = document.getElementById('btn-close');
  if (btnClose) btnClose.click();
});

// 通知主进程渲染进程已就绪
ipcRenderer.send('renderer-ready');

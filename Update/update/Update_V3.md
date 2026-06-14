# 番茄钟 v3 升级需求说明（v3.2）

## 项目背景
本地番茄钟桌面应用，基于 Flask + SQLite + pywebview 打包。

- **源码目录**：`C:\Users\BHkx\Desktop\first-cc\`
- **打包产物**：`C:\Users\BHkx\Desktop\first-cc\dist\Pomodoro.exe`（升级后必须重新打包覆盖）
- **数据文件**：`C:\Users\BHkx\Desktop\first-cc\dist\pomodoro.db`（升级必须向后兼容，不能丢旧数据）
- **前一版本**：v3.1（标签目标数 + 每日/一次性模式）
- **本次升级版本**：v3.2

## 用户反馈来源
- `Update/issue/issue_02.md`（2026-06-14 18:32）— 计时冻结 + 热力图遮挡 + 深色不可见
- `Update/issue/issue_03.md`（2026-06-14 18:55）— 窗口缩放 + 关闭行为 + 白框 + Logo + 启动画面 + 圆形悬浮窗

---

## 一、计时器引擎修复（核心）

### 现状问题
计时器使用 `setInterval(timerTick, 1000)` 逐秒递减 `STATE.timeLeft`。当浏览器标签页切换到后台时，Chrome/Edge 会将 `setInterval` 节流至 ~1 次/分钟，导致计时器实际上"冻结"，切回标签页才继续走。

### 修复方案：墙钟时间戳计时
- `timerTick()` 不再依赖 setInterval 调用次数，改为用 `Date.now() - tickStartedAt` 计算实际经过秒数
- setInterval 仍然维持 1 秒周期，但仅用于触发 UI 刷新，不承担计时精度职责
- 即使 setInterval 被节流到 60 秒才触发一次，切回后时间也能瞬间跳到正确值

### 实现细节
- `STATE` 新增 `tickStartedAt`（本轮计时开始的 `Date.now()`）和 `tickBaseLeft`（开始时的剩余秒数）
- `startTimer()` 记录时间戳基准
- `_stopTimer()` 清零时间戳（复用此前 `/simplify` 提取的辅助函数）
- `switchToMode()` / `resetTimerState()` 通过 `_stopTimer()` 清理
- `pauseTimer()` 暂停后下次 `startTimer()` 会重新记录基准（支持暂停恢复）

### 文件改动
- `static/app.js`：`timerTick()`, `startTimer()`, `pauseTimer()`, `_stopTimer()`, `switchToMode()`, `resetTimerState()`

---

## 二、页面可见性 API 监听

用户切回标签页时立即同步计时器显示，不用等下一个 setInterval 周期：

```js
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && STATE.isRunning) {
    timerTick(); // 立即同步
  }
});
```

### 文件改动
- `static/app.js`（`init()` 函数内）

---

## 三、热力图 Tooltip 修复

### 3a. Tooltip 视口边界裁剪

**问题**：tooltip 始终显示在鼠标 `(clientX+14, clientY-50)` 处，无边界检测。当鼠标靠近视口右侧/顶部/底部时，tooltip 被浏览器视口裁剪。

**修复**：`mousemove` 中添加边界翻转逻辑：
- 右侧超出 → 翻转到鼠标左侧
- 顶部超出 → 翻转到鼠标下方
- 底部超出 → 上移贴底

使用固定预估值 `EST_TW=200` / `EST_TH=60` 代替 `getBoundingClientRect()`（避免 mousemove 中每秒 30 次强制回流）。

### 3b. 深色模式空格子不可见

**问题**：深色主题下 `--hm-empty: #161B22` 与卡片背景 `--card-bg: #161B22` 完全相同，空格子与背景融为一体。

**修复**：`--hm-empty` 改为 `#1D2633`（比背景稍亮，可感知但保持低调）。

### 3c. Tooltip 颜色随主题切换

**问题**：三个 tooltip（`.hm-tooltip`、`.chart-tooltip`、`.mini-bar-tip`）的背景和文字颜色硬编码为 `#1E293B` / `#F1F5F9`，不随主题切换。

**修复**：新增 CSS 变量 `--tooltip-bg` / `--tooltip-text`，浅色和深色主题各自定义，三个 tooltip 统一使用变量。

### 文件改动
- `static/app.js`：`attachHmTooltip()` 的 `mousemove` 事件
- `static/style.css`：CSS 变量定义 + tooltip 样式

---

## 四、桌面窗口外观升级

### 4a. 窗口最小尺寸放宽

`min_size` 从 `(420, 640)` 改为 `(320, 480)`，允许缩得更小。

### 4b. 无边框窗口 (Frameless)

**问题**：Windows 原生窗口框架产生白色边框，与深色主题不协调，四角不够圆润。

**修复**：
- `webview.create_window(frameless=True, easy_drag=True)` — 移除原生标题栏
- 新增 HTML `.custom-titlebar` 自定义标题栏：
  - 左侧：番茄 Logo + "番茄钟" 品牌名（可拖拽区域）
  - 右侧：最小化按钮（─）、关闭按钮（✕）
  - 关闭按钮 hover 变红
- 标题栏 CSS：`-webkit-app-region: drag`（支持拖拽移动窗口）

### 文件改动
- `app.py`：`run_desktop_mode()` 窗口参数
- `static/index.html`：`.custom-titlebar` 元素
- `static/style.css`：标题栏样式

---

## 五、关闭行为改进

### 需求
关闭窗口时根据计时状态给出不同行为：
- 未计时 → 直接关闭
- 计时进行中 → 弹窗选择"关闭并保存"或"最小化到悬浮窗"

### 实现
- **关闭弹窗** (`#close-modal`)：复用已有 `.modal-overlay` 模式
  - "关闭并保存进度"：调用 `handleCloseWithSave()` 保存已用时长 → 退出
  - "最小化到悬浮窗"：同步状态到服务端 → 启动圆形悬浮窗 → 最小化主窗口
- **JS-Python 桥接** (`Api` 类)：
  - `minimize()` — 最小化主窗口
  - `close_app()` — 退出应用
  - `show_mini()` — 启动圆形悬浮窗
  - `hide_mini()` — 关闭悬浮窗
  - `update_timer_state(state)` — 同步计时状态到服务端
- **计时状态同步**：主窗口在状态变化时 PUT 到 `/api/timer-state`，迷你窗每秒 GET 轮询

### 文件改动
- `app.py`：`Api` 类 + `/api/timer-state` 路由（GET/PUT）
- `static/index.html`：`#close-modal` 弹窗
- `static/app.js`：`syncTimerState()`, `handleCloseWithSave()`, 标题栏按钮事件

---

## 六、圆形悬浮窗

### 需求
最小化后显示一个圆形悬浮窗，置顶在屏幕右下角，显示当前计时状态。

### 技术方案
- 独立 pywebview frameless 窗口（210x240），始终置顶
- HTML 内容用 CSS `border-radius: 50%` 做成圆形
- 显示：番茄 emoji + 剩余时间（MM:SS 大字体）+ 模式文字 + 暂停/继续 + 终止按钮
- 圆环边框颜色随模式变化（专注红 / 短休息绿 / 长休息蓝）
- 点击圆形 → 关闭悬浮窗，用户可手动恢复主窗口
- 计时基于本地 `Date.now()` 计算（与主窗口相同的墙钟逻辑），配合每秒轮询 `/api/timer-state` 保持同步

### 新文件
- `static/mini.html` — 圆形悬浮窗页面
- `static/mini.css` — 圆形布局样式

### app.py 新增路由
- `GET /mini` → 返回 `mini.html`
- `GET /api/timer-state` → 返回当前计时状态
- `PUT /api/timer-state` → 更新计时状态

---

## 七、应用图标 / Logo

1. 从 icons8 下载番茄图标 → `static/icon.png`（256x256 PNG）
2. 用 Pillow 生成多尺寸 `static/tomato.ico`（256/64/48/32/16）
3. `index.html` 添加 `<link rel="icon" href="/icon.png">`（浏览器标签页图标）
4. `webview.create_window(icon=...)` 设置窗口图标（任务栏图标）
5. 系统托盘图标优先使用 `icon.png`，回退到代码绘制

### 新文件
- `static/icon.png`
- `static/tomato.ico`

---

## 八、启动画面 + 激励词

打开软件时显示全屏 overlay：
- 番茄 Logo 图标 + "🍅 番茄钟" 标题 + 随机激励词
- 1.8 秒后自动淡出（CSS transition opacity 0.5s）
- 激励词库（10 条内置）：

```
专注当下，未来自然来
每一个番茄，都是对自己的承诺
深度工作，从此刻开始
心无旁骛，方能致远
最好的投资，是投资自己的时间
不积跬步，无以至千里
今天的努力，是明天的底气
静下心来，世界都是你的
番茄虽小，坚持就是力量
专注 25 分钟，改变每一天
```

### 文件改动
- `static/index.html`：`#splash-screen` 元素
- `static/style.css`：启动画面样式 + `splashIn` 动画
- `static/app.js`：`showSplash()` 函数（随机选词 + 定时淡出）

---

## 九、代码质量优化（`/simplify` 清理）

根据 `/simplify` 的四维度审查结果，应用了两项优化：

1. **提取 `_stopTimer()` 辅助函数**：`switchToMode()` 和 `resetTimerState()` 中重复的 5 行计时停止逻辑提取为单一入口
2. **移除 `getBoundingClientRect()` 调用**：tooltip `mousemove` 中用固定预估值代替，避免每秒 30+ 次强制回流

---

## 十、技术约束（保持不变）
- 后端：Flask + SQLite（`sqlite3` 模块，无 ORM）
- 前端：原生 JS + CSS，无框架无构建工具
- 离线运行，无外部网络请求（图标已下载到本地）
- pywebview 打包，exe 输出到 `dist/Pomodoro.exe`
- 计时状态全在前端 JS（`STATE` 对象），后端只是 REST API
- 数据库向前兼容：`pomodoro.db` 表结构无变化，无数据迁移

---

## 十一、改动文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `app.py` | 修改 | 窗口参数 (frameless/min_size/icon)、Api 类 (JS桥接)、路由 (/mini + /api/timer-state)、系统托盘图标 |
| `static/index.html` | 修改 | 自定义标题栏、关闭弹窗、启动画面、favicon |
| `static/style.css` | 修改 | 标题栏样式、tooltip 变量、启动画面样式、深色 hm-empty |
| `static/app.js` | 修改 | 墙钟计时、visibility 监听、syncTimerState、handleCloseWithSave、启动画面 |
| `static/mini.html` | **新增** | 圆形悬浮窗页面 |
| `static/mini.css` | **新增** | 圆形悬浮窗样式 |
| `static/icon.png` | **新增** | 应用图标 (256x256) |
| `static/tomato.ico` | **新增** | Windows 图标 (多尺寸) |

---

## 十二、新增 API 清单

| 方法 | 路由 | 用途 |
|------|------|------|
| GET | `/mini` | 返回迷你悬浮窗页面 |
| GET | `/api/timer-state` | 获取当前计时状态（供迷你窗轮询） |
| PUT | `/api/timer-state` | 更新计时状态（主窗口/迷你窗同步） |

---

## 十三、交付要求

1. **本地验证**：
   ```bash
   python app.py --browser
   ```
   手动验证：
   - 开始计时 → 切换标签页 30 秒 → 切回确认时间正确跳变
   - 热力图悬停 tooltip 不超出视口边界
   - 深色模式下空格子可见、tooltip 颜色随主题切换
   - 窗口可缩到 320x480
   - 无边框窗口无白框、标题栏可拖拽
   - 开始计时 → 点关闭 → 弹窗 → "关闭并保存" → 进度存入数据库
   - 开始计时 → 点关闭 → "最小化到悬浮窗" → 圆形窗出现
   - 启动时看到启动画面 → 1.8s 淡出
   - 任务栏显示番茄图标

2. **重新打包**：
   ```bash
   pyinstaller Pomodoro.spec
   ```
   覆盖 `dist/Pomodoro.exe`

3. **交付物**：
   - 修改后的所有源码文件（见文件清单）
   - 本变更说明文档 `Update_V3.md`
   - 重新打包后的 `dist/Pomodoro.exe`

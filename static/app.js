/* ═══════════════════════════════════════════════════════════
   番茄钟 Pomodoro Timer — 前端逻辑
   计时器 · 热力图 · Canvas 折线图 · 统计卡片 · 反思 · 导出
   ═══════════════════════════════════════════════════════════ */

// ── 全局状态 ──────────────────────────────────────────────
const STATE = {
  // 计时
  mode: 'work',          // 'work' | 'short_break' | 'long_break'
  timeLeft: 25 * 60,
  totalTime: 25 * 60,
  isRunning: false,
  pomodoroCount: 0,      // 今日已完成番茄数
  sessionStart: null,    // 当前 session 开始时间 ISO
  completedSession: null,// 刚结束的 session 数据（供反思用）
  tickStartedAt: 0,      // 本轮计时开始的 Date.now()（墙钟时间戳）
  tickBaseLeft: 0,       // 本轮计时开始时的 timeLeft

  // UI
  currentView: 'timer',
  dashboardTab: 'heatmap',

  // 热力图
  hmView: 'year',        // 'year' | 'month'
  hmYear: new Date().getFullYear(),
  hmMonth: new Date().getMonth() + 1,

  // 趋势图
  trendGran: 'day',      // 'day' | 'week' | 'month'

  // 设置（从服务器加载）
  settings: {},

  // 标签缓存
  allTagObjects: [],      // v3: 完整标签对象 [{id, name, color, icon, created_at}]
  selectedTag: null,       // v3: 当前选中的标签对象
  lastTag: '',             // v3: 上次使用的标签名
};

const RING_CIRCUMFERENCE = 2 * Math.PI * 130; // ~816.8

// ── 工具函数 ──────────────────────────────────────────────

function fmtTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function fmtHoursMinutes(totalMinutes) {
  if (totalMinutes <= 0) return '0h 0m';
  const h = Math.floor(totalMinutes / 60);
  const m = Math.round(totalMinutes % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function fmtMinutesOnly(totalMinutes) {
  const h = Math.floor(totalMinutes / 60);
  const m = Math.round(totalMinutes % 60);
  return `${h}h ${m}m`;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ═══════════════════════════════════════════════════════════
//  API 模块
// ═══════════════════════════════════════════════════════════

const API = {
  async getSettings() {
    const r = await fetch('/api/settings');
    return r.json();
  },
  async updateSettings(data) {
    const r = await fetch('/api/settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    return r.json();
  },
  async createRecord(data) {
    const r = await fetch('/api/records', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async getRecords(filters = {}) {
    const params = new URLSearchParams(filters).toString();
    const r = await fetch('/api/records?' + params);
    return r.json();
  },
  async getTodayStats() {
    const r = await fetch('/api/stats/today');
    return r.json();
  },
  async getSummary() {
    const r = await fetch('/api/stats/summary');
    return r.json();
  },
  async getHeatmap(view, year, month, tag) {
    const p = new URLSearchParams({ view, year: String(year), tag: tag || '' });
    if (month) p.set('month', String(month));
    const r = await fetch('/api/stats/heatmap?' + p.toString());
    return r.json();
  },
  async getTrend(granularity, tag) {
    const p = new URLSearchParams({ granularity, tag: tag || '' });
    const r = await fetch('/api/stats/trend?' + p.toString());
    return r.json();
  },
  async getByTag(period) {
    const r = await fetch('/api/stats/by-tag?period=' + (period || 'all'));
    return r.json();
  },
  async exportData(format) {
    const r = await fetch('/api/export?format=' + format);
    const blob = await r.blob();
    triggerDownload(blob, 'pomodoro_export.' + format);
  },

  // ── v3 标签管理 ──────────────────────────────────────────
  async getTags() {
    const r = await fetch('/api/tags');
    return r.json();
  },
  async createTag(data) {
    const r = await fetch('/api/tags', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async updateTag(id, data) {
    const r = await fetch('/api/tags/' + id, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async deleteTag(id) {
    const r = await fetch('/api/tags/' + id, { method: 'DELETE' });
    return r.json();
  },

  // ── v3 日明细 ────────────────────────────────────────────
  async getDayDetail(date) {
    const r = await fetch('/api/stats/day-detail?date=' + date);
    return r.json();
  },

  // ── v3 数据管理 ──────────────────────────────────────────
  async backup() {
    const r = await fetch('/api/backup');
    triggerDownload(await r.blob(), 'pomodoro_backup.zip');
  },
  async openDataFolder() {
    await fetch('/api/open-data-folder', { method: 'POST' });
  },
  async getDataPath() {
    const r = await fetch('/api/data-path');
    return r.json();
  },
};

// ═══════════════════════════════════════════════════════════
//  声音 & 通知
// ═══════════════════════════════════════════════════════════

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 200, 400].forEach(delay => {
      setTimeout(() => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = 880;
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.2);
      }, delay);
    });
  } catch (e) { /* 静默失败 */ }
}

function showNotification(title, body) {
  if (Notification.permission === 'granted') {
    new Notification(title, { body, icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="28" fill="%23E74C3C"/></svg>' });
  }
}

function requestNotification() {
  if (Notification.permission === 'default') {
    Notification.requestPermission();
  }
}

// ═══════════════════════════════════════════════════════════
//  撒花动画
// ═══════════════════════════════════════════════════════════

function triggerConfetti() {
  const container = _dom.confettiContainer;
  const colors = ['#FF6B6B', '#FECA57', '#48DBFB', '#FF9FF3', '#54A0FF', '#5F27CD', '#01A3A4', '#F368E0'];
  const frag = document.createDocumentFragment();

  for (let i = 0; i < 80; i++) {
    const piece = document.createElement('div');
    piece.className = 'confetti-piece';
    piece.style.left = Math.random() * 100 + '%';
    piece.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    piece.style.width = (8 + Math.random() * 10) + 'px';
    piece.style.height = (8 + Math.random() * 10) + 'px';
    piece.style.animationDuration = (2 + Math.random() * 3) + 's';
    piece.style.animationDelay = Math.random() * 2 + 's';
    piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
    frag.appendChild(piece);
  }
  container.appendChild(frag);

  setTimeout(() => { container.innerHTML = ''; }, 6000);
}

// ═══════════════════════════════════════════════════════════
//  计时器 模块
// ═══════════════════════════════════════════════════════════

let timerInterval = null;

function getModeLabel(mode) {
  return { work: '🍅 专注工作中', short_break: '☕ 短休息', long_break: '🌴 长休息' }[mode] || '';
}

function getModeColor(mode) {
  return { work: 'var(--accent)', short_break: 'var(--green)', long_break: 'var(--blue)' }[mode] || 'var(--accent)';
}

// DOM cache — populated once at init
const $ = (id) => document.getElementById(id);
let _dom = {};

function updateTimerDisplay() {
  const { mode, timeLeft, totalTime, isRunning, pomodoroCount } = STATE;
  const s = STATE.settings;

  _dom.timerText.textContent = fmtTime(timeLeft);
  _dom.timerMode.textContent = isRunning ? getModeLabel(mode) : (mode === 'work' ? '🍅 准备开始' : getModeLabel(mode));

  // 阶段文字
  const beforeLong = parseInt(s.pomodoros_before_long || 4);
  const longAfter = beforeLong - (pomodoroCount % beforeLong);
  _dom.timerPhase.textContent = mode === 'work'
    ? `第 ${pomodoroCount + 1} 个番茄 | ${longAfter} 个后长休息`
    : `已完成 ${pomodoroCount} 个番茄`;

  // 进度环
  const fraction = totalTime > 0 ? timeLeft / totalTime : 0;
  _dom.timerRing.style.strokeDasharray = RING_CIRCUMFERENCE;
  _dom.timerRing.style.strokeDashoffset = RING_CIRCUMFERENCE * (1 - fraction);
  _dom.timerRing.style.stroke = getModeColor(mode);

  // 按钮状态
  if (isRunning) {
    _dom.btnStart.textContent = '⏸  暂停';
    _dom.btnStart.style.background = 'var(--orange)';
    _dom.btnStop.disabled = false;
    _dom.btnSkip.disabled = true;
  } else {
    _dom.btnStart.textContent = '▶  开始';
    _dom.btnStart.style.background = getModeColor(mode);
    _dom.btnStop.disabled = (timeLeft === totalTime);
    _dom.btnSkip.disabled = false;
  }
}

function timerTick() {
  if (!STATE.isRunning) return;

  // 基于墙钟时间戳计算剩余秒数，不受浏览器后台节流影响
  const elapsed = Math.floor((Date.now() - STATE.tickStartedAt) / 1000);
  const newLeft = Math.max(0, STATE.tickBaseLeft - elapsed);

  if (newLeft !== STATE.timeLeft) {
    STATE.timeLeft = newLeft;
    updateTimerDisplay();
  }

  if (STATE.timeLeft <= 0) {
    onTimerEnd();
  }
}

function startTimer() {
  if (STATE.isRunning) {
    // 暂停
    pauseTimer();
    return;
  }

  STATE.isRunning = true;
  STATE.sessionStart = STATE.sessionStart || new Date().toISOString();
  STATE.tickStartedAt = Date.now();
  STATE.tickBaseLeft = STATE.timeLeft;

  // 保存 lastTag 到 settings
  if (STATE.selectedTag) {
    STATE.lastTag = STATE.selectedTag.name;
    API.updateSettings({ last_tag: STATE.selectedTag.name }).catch(() => {});
  } else {
    STATE.lastTag = '';
    API.updateSettings({ last_tag: '' }).catch(() => {});
  }

  // 锁定标签切换
  setTagsLocked(true);
  updateTimerDisplay();
  timerInterval = setInterval(timerTick, 1000);
}

function pauseTimer() {
  STATE.isRunning = false;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  setTagsLocked(false);
  updateTimerDisplay();
}

function stopTimer() {
  if (!STATE.sessionStart) return;

  const elapsedSec = STATE.totalTime - STATE.timeLeft;
  if (elapsedSec <= 0) return;  // 还没开始就不记录

  STATE.isRunning = false;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }

  const minutes = Math.round(elapsedSec / 60);
  const record = {
    date: new Date().toISOString().slice(0, 10),
    start_time: STATE.sessionStart,
    duration_minutes: minutes,
    status: 'abandoned',
    tag: STATE.selectedTag ? STATE.selectedTag.name : '',
  };

  API.createRecord(record).then(() => {
    resetTimerState();
    refreshAllData();
  });
}

function skipBreak() {
  switchToMode('work');
}

function onTimerEnd() {
  STATE.isRunning = false;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }

  if (STATE.mode === 'work') {
    // 番茄完成
    STATE.pomodoroCount++;
    const elapsedMin = Math.round(STATE.totalTime / 60);
    const record = {
      date: new Date().toISOString().slice(0, 10),
      start_time: STATE.sessionStart,
      duration_minutes: elapsedMin,
      status: 'completed',
      tag: STATE.selectedTag ? STATE.selectedTag.name : '',
    };

    STATE.completedSession = record;

    playBeep();
    showNotification('🍅 番茄完成！', `已完成 ${STATE.pomodoroCount} 个番茄，休息一下吧~`);

    // 重置计时状态
    resetTimerState();

    // 弹反思窗口
    showReflectionModal();

    // 刷新看板数据
    refreshAllData();

    // 短期：不自动开始休息（等用户关闭反思窗口后手动开始）
    updateTimerDisplay();
  } else {
    // 休息结束
    const breakName = STATE.mode === 'long_break' ? '长休息' : '短休息';
    playBeep();
    showNotification('⏰ 休息结束！', `${breakName}时间到，开始新的番茄吧！`);
    switchToMode('work');
    refreshAllData();
  }
}

function getDurations() {
  const s = STATE.settings;
  return {
    work: parseInt(s.work_duration || 25) * 60,
    short_break: parseInt(s.short_break_duration || 5) * 60,
    long_break: parseInt(s.long_break_duration || 15) * 60,
  };
}

function switchToMode(newMode) {
  STATE.mode = newMode;
  STATE.isRunning = false;
  STATE.sessionStart = null;
  STATE.tickStartedAt = 0;
  STATE.tickBaseLeft = 0;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }

  STATE.timeLeft = getDurations()[newMode];
  STATE.totalTime = STATE.timeLeft;
  updateTimerDisplay();
}

function resetTimerState() {
  STATE.isRunning = false;
  STATE.sessionStart = null;
  STATE.tickStartedAt = 0;
  STATE.tickBaseLeft = 0;
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }

  STATE.timeLeft = getDurations()[STATE.mode];
  STATE.totalTime = STATE.timeLeft;
  setTagsLocked(false);
  updateTimerDisplay();
}

// ═══════════════════════════════════════════════════════════
//  v3 标签选择器
// ═══════════════════════════════════════════════════════════

function setTagsLocked(locked) {
  _dom.tagChips.querySelectorAll('.tag-chip').forEach(c => c.classList.toggle('locked', locked));
}

async function renderTagChips() {
  const allTags = STATE.allTagObjects;
  const container = _dom.tagChips;

  // 差异检测（含进度数据）
  const fp = allTags.map(t => `${t.id}:${t.name}:${t.color}:${t.icon}:${t.today_done}:${t.all_done}:${t.target_pomodoros}:${t.tag_type}`).join(',')
           + '|sel=' + (STATE.selectedTag ? STATE.selectedTag.id : 'null')
           + '|run=' + STATE.isRunning;
  if (container._fp === fp && allTags.length > 0) return;
  container._fp = fp;

  if (allTags.length === 0) {
    container._fp = null;
    container.innerHTML = '<div class="tag-chips-empty">还没有标签，去「设置 → 标签管理」创建吧~</div>';
    return;
  }

  // 过滤：一次性标签已完成则隐藏
  const visible = allTags.filter(t => {
    if (t.tag_type === 'once' && t.target_pomodoros && (t.all_done || 0) >= t.target_pomodoros) return false;
    return true;
  });

  if (visible.length === 0) {
    container._fp = null;
    container.innerHTML = '<div class="tag-chips-empty">所有目标已完成 🎉，去「设置 → 标签管理」创建新标签吧~</div>';
    return;
  }

  container.innerHTML = visible.map(t => {
    const iconStr = t.icon ? `<span class="tag-chip-icon">${t.icon}</span>` : '';
    const selClass = (STATE.selectedTag && STATE.selectedTag.id === t.id) ? ' selected' : '';
    const lockedClass = STATE.isRunning ? ' locked' : '';
    // 进度（计算一次，复用）
    let progressHtml = '';
    let doneClass = '';
    if (t.target_pomodoros) {
      const done = t.tag_type === 'once' ? (t.all_done || 0) : (t.today_done || 0);
      const isDone = done >= t.target_pomodoros;
      progressHtml = isDone
        ? '<span class="tag-chip-progress">✓</span>'
        : `<span class="tag-chip-progress">${done}/${t.target_pomodoros}</span>`;
      if (isDone) doneClass = ' done';
    }
    return `<div class="tag-chip${selClass}${lockedClass}${doneClass}" data-tag-id="${t.id}" data-tag-name="${t.name}" data-tag-color="${t.color}" data-tag-icon="${t.icon || ''}">
      <span class="tag-chip-dot" style="background:${t.color}"></span>
      ${iconStr}
      <span>${t.name}</span>
      ${progressHtml}
    </div>`;
  }).join('');

  // 事件委托
  container.onclick = e => {
    if (STATE.isRunning) return;
    const chip = e.target.closest('.tag-chip');
    if (!chip || chip.classList.contains('done')) return;
    selectTagChip(chip);
  };

  container.ondblclick = e => {
    if (STATE.isRunning) return;
    const chip = e.target.closest('.tag-chip');
    if (!chip || chip.classList.contains('done')) return;
    selectTagChip(chip);
    if (STATE.mode === 'work') {
      startTimer();
    }
  };

  updateActiveTagDisplay();
}

function selectTagChip(chip) {
  const tagId = parseInt(chip.dataset.tagId);
  const existing = document.querySelector('.tag-chip.selected');
  if (existing && existing.dataset.tagId === String(tagId)) {
    // 再次点击取消选中
    STATE.selectedTag = null;
    existing.classList.remove('selected');
    updateActiveTagDisplay();
    return;
  }

  // 取消之前的选中
  document.querySelectorAll('.tag-chip.selected').forEach(c => c.classList.remove('selected'));

  // 选中当前
  chip.classList.add('selected');
  STATE.selectedTag = {
    id: tagId,
    name: chip.dataset.tagName,
    color: chip.dataset.tagColor,
    icon: chip.dataset.tagIcon,
  };
  updateActiveTagDisplay();
}

function updateActiveTagDisplay() {
  const display = _dom.activeTagDisplay;
  if (STATE.selectedTag) {
    display.style.display = 'flex';
    _dom.activeTagDot.style.background = STATE.selectedTag.color;
    _dom.activeTagName.textContent = STATE.selectedTag.name;
  } else {
    display.style.display = 'none';
  }
}

// ═══════════════════════════════════════════════════════════
//  反思弹窗
// ═══════════════════════════════════════════════════════════

function showReflectionModal() {
  const modal = _dom.reflectionModal;
  const stars = _dom.reflectionStars;
  const input = _dom.reflectionInput;

  // 重置
  stars.querySelectorAll('span').forEach(s => {
    s.classList.remove('active');
    s.textContent = '☆';
  });
  input.value = '';
  modal.classList.add('show');

  // 星级点击（仅控制样式）
  stars.querySelectorAll('span').forEach(span => {
    span.onclick = () => {
      const val = parseInt(span.dataset.star);
      stars.querySelectorAll('span').forEach((s, i) => {
        s.textContent = i < val ? '★' : '☆';
        s.classList.toggle('active', i < val);
      });
    };
  });
}

async function handleReflectionSubmit(extra) {
  const record = STATE.completedSession;
  if (!record) return;

  record.focus_score = extra.focus_score;
  record.reflection = extra.reflection;

  await API.createRecord(record);
  STATE.completedSession = null;

  // 根据番茄数决定休息类型
  const s = STATE.settings;
  const beforeLong = parseInt(s.pomodoros_before_long || 4);
  if (STATE.pomodoroCount % beforeLong === 0) {
    switchToMode('long_break');
  } else {
    switchToMode('short_break');
  }

  updateTimerDisplay();
  refreshAllData();
}

// ═══════════════════════════════════════════════════════════
//  每日目标进度
// ═══════════════════════════════════════════════════════════

let prevGoalPercent = 0;

async function updateDailyGoal() {
  const stats = await API.getTodayStats();
  const goalMin = stats.goal_minutes;
  const percent = Math.min(stats.goal_percent, 100);

  _dom.goalText.textContent =
    `${fmtMinutesOnly(stats.total_minutes)} / ${fmtMinutesOnly(goalMin)}`;
  _dom.goalFill.style.width = percent + '%';
  _dom.goalPercent.textContent = Math.round(percent) + '%';

  // 达成目标撒花
  if (percent >= 100 && prevGoalPercent < 100) {
    triggerConfetti();
    setTimeout(() => {
      alert('🎉 恭喜！今日学习目标已达成！');
    }, 500);
  }
  prevGoalPercent = percent;

  _dom.pomodoroCount.textContent = STATE.pomodoroCount;
  _dom.todayCount.textContent = stats.pomodoro_count;
}

// ═══════════════════════════════════════════════════════════
//  标签建议
// ═══════════════════════════════════════════════════════════

async function updateTagSuggestions() {
  // v3: 从 tags API 获取完整标签对象
  const tags = await API.getTags();
  STATE.allTagObjects = tags;
  // 恢复上次选中的标签
  if (STATE.lastTag && !STATE.isRunning) {
    const lastTagObj = tags.find(t => t.name === STATE.lastTag);
    if (lastTagObj) {
      STATE.selectedTag = lastTagObj;
    }
  }

  // 渲染标签选择器
  renderTagChips();

  // 更新看板筛选下拉
  const select = _dom.dashTagFilter;
  const currentVal = select.value;
  select.innerHTML = '<option value="">全部</option>' +
    tags.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
  select.value = currentVal;
}

// ═══════════════════════════════════════════════════════════
//  热力图
// ═══════════════════════════════════════════════════════════

function getHeatLevel(minutes) {
  if (minutes <= 0) return 0;
  if (minutes < 25) return 1;
  if (minutes < 60) return 2;
  if (minutes < 120) return 3;
  return 4;
}

async function renderHeatmap() {
  const { hmView, hmYear, hmMonth } = STATE;
  const tag = _dom.dashTagFilter.value;
  const result = await API.getHeatmap(hmView, hmYear, hmView === 'month' ? hmMonth : null, tag);
  const data = result.data || {};

  _dom.hmTitle.textContent =
    hmView === 'year' ? String(hmYear) : `${hmYear}年${String(hmMonth).padStart(2, '0')}月`;

  const container = _dom.heatmapContainer;

  if (hmView === 'year') {
    renderYearHeatmap(container, hmYear, data);
  } else {
    renderMonthHeatmap(container, hmYear, hmMonth, data);
  }

  // 更新标签下拉
  updateDashTagFilter(result.tags || []);
}

function renderYearHeatmap(container, year, data) {
  const dayNames = ['', '一', '', '三', '', '五', ''];  // 周一三五
  const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月',
                      '7月', '8月', '9月', '10月', '11月', '12月'];

  // 计算一年中所有的天及其位置
  const start = new Date(year, 0, 1);
  const end = new Date(year + 1, 0, 1);

  // 找出第一个周一（作为第一列）
  // GitHub 风格: 周日到周六列，但中文习惯周一到周日
  let firstMonday = new Date(start);
  while (firstMonday.getDay() !== 1) {
    firstMonday.setDate(firstMonday.getDate() - 1);
  }

  // 构建 weeks
  const weeks = [];
  let cur = new Date(firstMonday);
  while (cur < end || weeks.length < 53) {
    const week = [];
    for (let d = 0; d < 7; d++) {
      const dateStr = cur.toISOString().slice(0, 10);
      const inYear = cur.getFullYear() === year;
      const entry = data[dateStr];
      week.push({
        date: dateStr,
        minutes: entry ? entry.minutes : 0,
        count: entry ? entry.count : 0,
        inYear,
      });
      cur.setDate(cur.getDate() + 1);
    }
    weeks.push(week);
    // 防止无限循环
    if (cur > new Date(year + 1, 11, 31).getTime()) break;
  }

  // 计算月份标签位置（每月的第一个周一所在列）
  const monthPositions = [];
  for (let m = 0; m < 12; m++) {
    const first = new Date(year, m, 1);
    // 找到包含该日期的周列索引
    for (let wi = 0; wi < weeks.length; wi++) {
      const weekStart = new Date(weeks[wi][0].date);
      const weekEnd = new Date(weeks[wi][6].date);
      if (first >= weekStart && first <= weekEnd) {
        monthPositions.push({ name: monthNames[m], col: wi });
        break;
      }
    }
  }

  let html = '<div class="hm-year-wrapper">';

  // 日期标签列
  html += '<div class="hm-day-labels">';
  dayNames.forEach((name, i) => {
    html += `<div class="hm-day-label">${name}</div>`;
  });
  html += '</div>';

  // 主网格区域
  html += '<div>';
  // 月份标签
  html += '<div class="hm-month-labels" style="margin-left:0">';
  let lastCol = -1;
  monthPositions.forEach(mp => {
    const gap = mp.col - lastCol - 1;
    if (gap > 0) {
      html += `<span style="width:${gap * 14 + gap * 3}px;display:inline-block"></span>`;
    }
    // 估算每个月份标签宽度
    const labelWeeks = mp.col < 11 ? 5 : 4;
    html += `<span class="hm-month-label" style="width:${labelWeeks * 14 + (labelWeeks - 1) * 3 + 3}px">${mp.name}</span>`;
    lastCol = mp.col + labelWeeks - 1;
  });
  html += '</div>';

  // 单元格
  html += '<div class="hm-year-grid">';
  for (let wi = 0; wi < weeks.length; wi++) {
    html += '<div class="hm-week-col">';
    for (let di = 0; di < 7; di++) {
      const cell = weeks[wi][di];
      const level = cell.inYear ? getHeatLevel(cell.minutes) : -1;
      const cls = cell.inYear ? `c${level}` : '';
      const opacity = cell.inYear ? '' : 'opacity:0.3';
      html += `<div class="hm-cell ${cls}" style="${opacity}"
                    data-date="${cell.date}"
                    data-minutes="${cell.minutes}"
                    data-count="${cell.count}"
                    title="${cell.date}: ${fmtMinutesOnly(cell.minutes)} · ${cell.count}个番茄"></div>`;
    }
    html += '</div>';
  }
  html += '</div></div></div>';

  container.innerHTML = html;

  // Tooltip
  attachHmTooltip(container);
}

function renderMonthHeatmap(container, year, month, data) {
  const dayNames = ['一', '二', '三', '四', '五', '六', '日'];
  const firstDay = new Date(year, month - 1, 1);
  const lastDay = new Date(year, month, 0);
  const daysInMonth = lastDay.getDate();
  // 本月第一天是周几（0=周日，转换为 1=周一）
  let startDow = firstDay.getDay(); // 0=Sun
  startDow = startDow === 0 ? 6 : startDow - 1; // 转为 0=Mon

  let html = '<div class="hm-month-grid">';

  // 日期头
  dayNames.forEach(d => {
    html += `<div class="hm-month-dayname">${d}</div>`;
  });

  // 前置空单元格
  for (let i = 0; i < startDow; i++) {
    html += '<div class="hm-month-cell empty"></div>';
  }

  // 日期单元格
  const todayStr = new Date().toISOString().slice(0, 10);
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const entry = data[dateStr];
    const minutes = entry ? entry.minutes : 0;
    const count = entry ? entry.count : 0;
    const level = getHeatLevel(minutes);
    const isToday = dateStr === todayStr;
    html += `<div class="hm-month-cell c${level}"
                  style="${isToday ? 'outline:2px solid var(--accent);outline-offset:1px' : ''}"
                  data-date="${dateStr}"
                  data-minutes="${minutes}"
                  data-count="${count}"
                  title="${dateStr}: ${fmtMinutesOnly(minutes)} · ${count}个番茄">${d}</div>`;
  }

  html += '</div>';
  container.innerHTML = html;

  attachHmTooltip(container);
}

// Tooltip singleton — created once, reused via event delegation
let _hmTooltip = null;
let _hmTooltipCache = {};  // v3: 缓存 day-detail 结果

function attachHmTooltip(container) {
  if (!_hmTooltip) {
    _hmTooltip = document.createElement('div');
    _hmTooltip.className = 'hm-tooltip';
    document.body.appendChild(_hmTooltip);
  }

  container.onmouseover = async e => {
    const cell = e.target.closest('[data-date]');
    if (!cell) return;
    const d = cell.dataset;
    const minutes = parseInt(d.minutes) || 0;
    if (minutes === 0 && parseInt(d.count || 0) === 0) {
      // 无记录不弹 tooltip
      _hmTooltip.classList.remove('show');
      return;
    }

    // 先显示基础信息
    _hmTooltip.innerHTML = `<strong>${d.date}</strong><br>总专注: ${fmtMinutesOnly(minutes)}<br>番茄: ${d.count} 个<br><span style="color:#94A3B8;font-size:11px">加载明细...</span>`;
    _hmTooltip.classList.add('show');
    _hmTooltip._date = d.date;

    // 异步加载日明细
    const dateKey = d.date;
    if (!_hmTooltipCache[dateKey]) {
      _hmTooltipCache[dateKey] = API.getDayDetail(dateKey);
    }
    const detail = await _hmTooltipCache[dateKey];

    // 确保 tooltip 还在同一日期上
    if (_hmTooltip._date !== d.date) return;

    let html = `<strong>${d.date}</strong>`;
    html += `<hr class="hm-tooltip-divider">`;
    html += `总专注: ${fmtMinutesOnly(detail.total_minutes)}<br>`;
    html += `番茄数: ${detail.total_count} 个`;

    if (detail.details && detail.details.length > 0) {
      html += `<hr class="hm-tooltip-divider">`;
      detail.details.forEach(td => {
        html += `<div class="hm-tooltip-tag-row">
          <span class="hm-tooltip-tag-dot" style="background:${td.color}"></span>
          ${td.tag} &nbsp;${fmtMinutesOnly(td.total_minutes)}（${td.count} 个番茄）
        </div>`;
      });
    }

    _hmTooltip.innerHTML = html;
  };

  container.onmousemove = e => {
    // 边界检测：tooltip 靠近视口边缘时翻转到另一侧，避免被裁剪
    const rect = _hmTooltip.getBoundingClientRect();
    const tw = rect.width || 200;   // 首次渲染前用预估值
    const th = rect.height || 60;

    let left = e.clientX + 14;
    let top = e.clientY - 50;

    // 右侧超出 → 翻转到鼠标左侧
    if (left + tw > window.innerWidth - 8) {
      left = e.clientX - tw - 14;
    }
    // 顶部超出 → 翻转到鼠标下方
    if (top < 8) {
      top = e.clientY + 20;
    }
    // 底部超出 → 上移
    if (top + th > window.innerHeight - 8) {
      top = window.innerHeight - th - 8;
    }

    _hmTooltip.style.left = left + 'px';
    _hmTooltip.style.top = top + 'px';
  };

  container.onmouseout = e => {
    if (e.target.closest('[data-date]')) {
      _hmTooltip.classList.remove('show');
    }
  };
}

function updateDashTagFilter(tags) {
  const select = _dom.dashTagFilter;
  if (!tags || !tags.length) return;

  const existing = new Set(Array.from(select.options).map(o => o.value));
  let html = '';
  tags.forEach(t => {
    if (!existing.has(t)) {
      html += `<option value="${t}">${t}</option>`;
    }
  });
  if (html) select.insertAdjacentHTML('beforeend', html);
}

// ═══════════════════════════════════════════════════════════
//  Canvas 趋势折线图
// ═══════════════════════════════════════════════════════════

async function renderTrendChart() {
  const gran = STATE.trendGran;
  const tag = _dom.dashTagFilter.value;
  const result = await API.getTrend(gran, tag);
  const chartData = result.data || [];
  const goalMinutes = result.goal_minutes || 120;

  const canvas = _dom.trendCanvas;
  const wrapper = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cs = getComputedStyle(document.documentElement);  // cache — called many times below

  // 设置 canvas 分辨率
  const rect = wrapper.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = 300 * dpr;
  canvas.style.width = rect.width + 'px';
  canvas.style.height = '300px';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const W = rect.width;
  const H = 300;

  // 边距
  const margin = { top: 20, right: 20, bottom: 50, left: 55 };
  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;

  // 清空 & 背景
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = cs.getPropertyValue('--card-bg').trim();
  ctx.fillRect(0, 0, W, H);

  // 如果没有数据
  if (chartData.length === 0) {
    ctx.fillStyle = cs.getPropertyValue('--text-muted').trim();
    ctx.font = '14px "Microsoft YaHei UI"';
    ctx.textAlign = 'center';
    ctx.fillText('暂无数据，开始专注吧~', W / 2, H / 2);
    return;
  }

  // 数据范围
  const maxVal = Math.max(goalMinutes, ...chartData.map(d => d.minutes || 0), 1);
  const yMax = Math.ceil(maxVal / 60) * 60; // 取整到小时
  const yTicks = Math.min(6, Math.ceil(yMax / 60) + 1);

  // 预取颜色
  const colBorder = cs.getPropertyValue('--border').trim();
  const colMuted = cs.getPropertyValue('--text-muted').trim();
  const colAccent = cs.getPropertyValue('--accent').trim();
  const colOrange = cs.getPropertyValue('--orange').trim() || '#E67E22';

  // Y 轴 & 网格
  ctx.strokeStyle = colBorder;
  ctx.fillStyle = colMuted;
  ctx.font = '11px "Microsoft YaHei UI"';
  ctx.textAlign = 'right';
  ctx.lineWidth = 1;

  for (let i = 0; i <= yTicks; i++) {
    const val = (yMax / yTicks) * i;
    const y = margin.top + plotH - (val / yMax) * plotH;

    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(W - margin.right, y);
    ctx.stroke();

    const label = (val / 60).toFixed(1) + 'h';
    ctx.fillText(label, margin.left - 8, y + 4);
  }

  // X 轴标签
  ctx.textAlign = 'center';
  const maxLabels = Math.min(chartData.length, gran === 'day' ? 12 : gran === 'week' ? 12 : 6);
  const labelStep = Math.max(1, Math.floor(chartData.length / maxLabels));

  for (let i = 0; i < chartData.length; i += labelStep) {
    const x = margin.left + (i / (chartData.length - 1 || 1)) * plotW;
    const label = (chartData[i].date || chartData[i].period || '').slice(5); // MM-DD
    ctx.fillText(label, x, H - margin.bottom + 20);
  }

  // 目标虚线
  const goalY = margin.top + plotH - (goalMinutes / yMax) * plotH;
  ctx.beginPath();
  ctx.setLineDash([6, 4]);
  ctx.strokeStyle = colOrange;
  ctx.lineWidth = 1.5;
  ctx.moveTo(margin.left, goalY);
  ctx.lineTo(W - margin.right, goalY);
  ctx.stroke();
  ctx.setLineDash([]);

  // 目标标签
  ctx.fillStyle = colOrange;
  ctx.textAlign = 'left';
  ctx.font = '10px "Microsoft YaHei UI"';
  ctx.fillText('目标 ' + (goalMinutes / 60).toFixed(1) + 'h', W - margin.right + 2, goalY + 4);

  // 数据折线
  ctx.beginPath();
  ctx.strokeStyle = colAccent;
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  for (let i = 0; i < chartData.length; i++) {
    const x = margin.left + (i / (chartData.length - 1 || 1)) * plotW;
    const y = margin.top + plotH - ((chartData[i].minutes || 0) / yMax) * plotH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // 渐变填充
  ctx.lineTo(margin.left + plotW, margin.top + plotH);
  ctx.lineTo(margin.left, margin.top + plotH);
  ctx.closePath();
  const gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
  gradient.addColorStop(0, colAccent + '40');
  gradient.addColorStop(1, colAccent + '05');
  ctx.fillStyle = gradient;
  ctx.fill();

  // 数据点
  const dotStep = Math.max(1, Math.floor(chartData.length / 30));
  for (let i = 0; i < chartData.length; i += dotStep) {
    const x = margin.left + (i / (chartData.length - 1 || 1)) * plotW;
    const y = margin.top + plotH - ((chartData[i].minutes || 0) / yMax) * plotH;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = colAccent;
    ctx.fill();
  }
}

// ═══════════════════════════════════════════════════════════
//  统计卡片
// ═══════════════════════════════════════════════════════════

async function renderStatsCards() {
  const summary = await API.getSummary();

  document.getElementById('card-today').textContent = fmtMinutesOnly(summary.today.total_minutes);
  document.getElementById('card-today-percent').textContent = '目标 ' + summary.today.goal_percent + '%';
  document.getElementById('card-week').textContent = fmtMinutesOnly(summary.week.total_minutes);
  document.getElementById('card-week-avg').textContent = '日均 ' + fmtMinutesOnly(summary.week.avg_daily);
  document.getElementById('card-month').textContent = fmtMinutesOnly(summary.month.total_minutes);
  document.getElementById('card-month-avg').textContent = '日均 ' + fmtMinutesOnly(summary.month.avg_daily);
  document.getElementById('card-streak').textContent = summary.streak + ' 天';
  document.getElementById('card-total').textContent = fmtHoursMinutes(summary.total_all_time);

  const tags = summary.top_tags || [];
  if (tags.length > 0) {
    document.getElementById('card-tags').textContent = tags.map(t => t.tag).join(' / ');
    document.getElementById('card-tags-sub').textContent = tags.map(t => t.count + '次').join(' · ');
  } else {
    document.getElementById('card-tags').textContent = '—';
    document.getElementById('card-tags-sub').textContent = '暂无数据';
  }

  // 同时也刷新标签明细
  renderTagBreakdown();
}

// ── 按标签/项目统计明细 (v3 升级) ──────────────────────────

async function renderTagBreakdown() {
  // 读取时间筛选按钮组
  const activeBtn = document.querySelector('#tag-period-btns .tp-btn.active');
  const period = activeBtn ? activeBtn.dataset.period : 'all';
  const data = await API.getByTag(period);
  const tags = data.tags || [];
  const totalMin = data.total_minutes || 0;
  const maxMin = tags.length > 0 ? Math.max(...tags.map(t => t.total_minutes)) : 1;

  // 总计摘要
  document.getElementById('tag-breakdown-grand').textContent =
    `总计 ${data.total_pomodoros} 个番茄 · ${fmtHoursMinutes(totalMin)}`;

  // 列表
  const list = document.getElementById('tag-breakdown-list');
  if (tags.length === 0) {
    list.innerHTML = '<div class="tag-breakdown-empty">还没有带标签的专注记录，去选一个标签开始吧 🎯</div>';
    return;
  }

  list.innerHTML = tags.map((t, i) => {
    const pct = totalMin > 0 ? Math.max(2, Math.round((t.total_minutes / totalMin) * 100)) : 0;
    const color = t.color || '#94A3B8';
    return `
      <div class="tag-detail-row" data-tag-name="${t.tag}">
        <div class="tag-detail-left">
          <span class="tag-detail-dot" style="background:${color}"></span>
          <span class="tag-detail-name">${t.icon ? t.icon + ' ' : ''}${t.tag}</span>
        </div>
        <div class="tag-detail-bar-wrap">
          <div class="tag-detail-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="tag-detail-right">${t.count} 个番茄 · ${fmtHoursMinutes(t.total_minutes)}</div>
      </div>
      <div class="mini-bars-row" id="mini-${i}" data-tag="${t.tag}"></div>`;
  }).join('');

  // 绑定点击联动 → 切到热力图 + 筛选
  list.querySelectorAll('.tag-detail-row').forEach(row => {
    row.addEventListener('click', () => {
      const tagName = row.dataset.tagName;
      // 切到看板
      switchView('dashboard');
      // 切到热力图子页
      switchDashTab('heatmap');
      // 设置筛选
      _dom.dashTagFilter.value = tagName;
      // 刷新热力图
      renderHeatmap();
    });
  });

  // 异步加载迷你柱状图
  tags.forEach((t, i) => {
    renderMiniBars(t.tag, i);
  });
}

async function renderMiniBars(tagName, idx) {
  const container = document.getElementById('mini-' + idx);
  if (!container) return;

  // 查询最近 7 天（含今天）
  const today = new Date();
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().slice(0, 10));
  }

  // 获取该标签最近 7 天的趋势数据（使用 trend API 按天）
  try {
    const result = await API.getTrend('day', tagName);
    const trendData = result.data || [];
    // 筛选最近 7 天
    const recentMap = {};
    trendData.forEach(d => { recentMap[d.date] = d.minutes || 0; });

    const maxVal = Math.max(1, ...days.map(d => recentMap[d] || 0));
    const color = STATE.allTagObjects.find(t => t.name === tagName)?.color || '#94A3B8';

    container.innerHTML = days.map(date => {
      const mins = recentMap[date] || 0;
      const h = mins > 0 ? Math.max(4, (mins / maxVal) * 28) : 4;
      const cls = mins > 0 ? '' : ' empty';
      return `<div class="mini-bar${cls}" style="height:${h}px;background:${mins > 0 ? color : ''}">
        ${mins > 0 ? `<span class="mini-bar-tip">${date.slice(5)}<br>${fmtHoursMinutes(mins)}</span>` : ''}
      </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = '';
  }
}

// ═══════════════════════════════════════════════════════════
//  v3 标签管理（设置页）
// ═══════════════════════════════════════════════════════════

const PRESET_COLORS = [
  '#E74C3C', '#E67E22', '#F1C40F', '#27AE60',
  '#1ABC9C', '#2980B9', '#8E44AD', '#E91E90'
];

async function renderTagManagement(providedTags) {
  const tags = providedTags || await API.getTags();
  if (!providedTags) STATE.allTagObjects = tags;

  const container = document.getElementById('tag-mgmt-list');
  if (tags.length === 0) {
    container.innerHTML = '<div class="tag-mgmt-empty">暂无标签，点击下方按钮创建第一个</div>';
    return;
  }

  container.innerHTML = tags.map(t => `
    <div class="tag-mgmt-row">
      <div class="tag-mgmt-info">
        <span class="tag-mgmt-dot" style="background:${t.color}"></span>
        ${t.icon ? `<span class="tag-mgmt-icon">${t.icon}</span>` : ''}
        <span class="tag-mgmt-name">${t.name}</span>
      </div>
      <div class="tag-mgmt-actions">
        <button class="btn-edit-tag" data-id="${t.id}">✏ 编辑</button>
        <button class="btn-del btn-del-tag" data-id="${t.id}" data-name="${t.name}">✕ 删除</button>
      </div>
    </div>
  `).join('');

  // 绑定编辑按钮
  container.querySelectorAll('.btn-edit-tag').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = parseInt(btn.dataset.id);
      const tag = tags.find(t => t.id === id);
      if (tag) showTagEditModal(tag);
    });
  });

  // 绑定删除按钮
  container.querySelectorAll('.btn-del-tag').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = parseInt(btn.dataset.id);
      const name = btn.dataset.name;
      if (confirm(`确定删除标签「${name}」？\n\n删除后历史记录中的标签数据仍会保留，只是此标签将不再出现在选择器中。`)) {
        API.deleteTag(id).then(async res => {
          if (res.ok) {
            await updateTagSuggestions();           // 拉取标签、更新 STATE、渲染 chips
            renderTagManagement(STATE.allTagObjects); // 复用已加载的数据
          } else {
            alert('删除失败: ' + (res.error || '未知错误'));
          }
        });
      }
    });
  });
}

function showTagEditModal(tag) {
  const modal = document.getElementById('tag-edit-modal');
  const title = document.getElementById('tag-edit-title');
  const nameInput = document.getElementById('tag-edit-name');
  const iconInput = document.getElementById('tag-edit-icon');
  const targetInput = document.getElementById('tag-edit-target');
  const colorsContainer = document.getElementById('tag-edit-colors');
  const charCount = document.getElementById('tag-char-count');
  const typeToggle = document.getElementById('tag-edit-type');

  // 当前编辑的标签 id（null = 新增）
  modal._tagId = tag ? tag.id : null;
  title.textContent = tag ? '编辑标签' : '新增标签';

  nameInput.value = tag ? tag.name : '';
  iconInput.value = tag ? (tag.icon || '') : '';
  targetInput.value = (tag && tag.target_pomodoros) ? tag.target_pomodoros : '';
  charCount.textContent = (tag ? tag.name.length : 0) + '/12';

  // 类型切换
  let selectedType = (tag && tag.tag_type) ? tag.tag_type : 'daily';
  typeToggle.querySelectorAll('.tt-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.type === selectedType);
  });
  typeToggle.onclick = e => {
    const btn = e.target.closest('.tt-btn');
    if (!btn) return;
    typeToggle.querySelectorAll('.tt-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedType = btn.dataset.type;
  };

  // 颜色选择器
  let selectedColor = tag ? tag.color : PRESET_COLORS[0];
  colorsContainer.innerHTML = PRESET_COLORS.map(c =>
    `<span class="color-picker-dot${c === selectedColor ? ' selected' : ''}"
           style="background:${c}" data-color="${c}"></span>`
  ).join('');
  colorsContainer.onclick = e => {
    const dot = e.target.closest('.color-picker-dot');
    if (!dot) return;
    colorsContainer.querySelectorAll('.color-picker-dot').forEach(d => d.classList.remove('selected'));
    dot.classList.add('selected');
    selectedColor = dot.dataset.color;
  };

  // 字符计数
  nameInput.oninput = () => {
    charCount.textContent = nameInput.value.length + '/12';
  };

  // 保存逻辑
  const saveBtn = document.getElementById('btn-tag-edit-save');
  const cancelBtn = document.getElementById('btn-tag-edit-cancel');

  const onSave = async () => {
    const name = nameInput.value.trim();
    if (!name || name.length > 12) {
      alert('标签名需 1-12 个字符');
      return;
    }
    const targetVal = parseInt(targetInput.value);
    const data = {
      name, color: selectedColor, icon: iconInput.value.trim(),
      target_pomodoros: (targetVal >= 1 && targetVal <= 20) ? targetVal : null,
      tag_type: selectedType,
    };
    let result;
    if (modal._tagId) {
      result = await API.updateTag(modal._tagId, data);
    } else {
      result = await API.createTag(data);
    }
    if (result.ok) {
      modal.classList.remove('show');
      await updateTagSuggestions();
      renderTagManagement(STATE.allTagObjects);
    } else {
      alert('操作失败: ' + (result.error || '未知错误'));
    }
  };

  const onCancel = () => { modal.classList.remove('show'); };

  // 键盘：Enter 保存 / Esc 取消（先移除旧监听器防累积）
  if (modal._onKey) modal.removeEventListener('keydown', modal._onKey);
  modal._onKey = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); onSave(); }
    if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
  };
  modal.addEventListener('keydown', modal._onKey);

  // cloneNode 清理旧监听器（闭包引用每次不同，removeEventListener 不可靠）
  saveBtn.replaceWith(saveBtn.cloneNode(true));
  cancelBtn.replaceWith(cancelBtn.cloneNode(true));
  document.getElementById('btn-tag-edit-save').addEventListener('click', onSave);
  document.getElementById('btn-tag-edit-cancel').addEventListener('click', onCancel);

  modal.classList.add('show');
  nameInput.focus();
}

// ═══════════════════════════════════════════════════════════
//  v3 数据管理（设置页）
// ═══════════════════════════════════════════════════════════

async function loadDataPath() {
  try {
    const info = await API.getDataPath();
    document.getElementById('data-path-display').value = info.db_path;
  } catch (e) {
    document.getElementById('data-path-display').value = '加载失败';
  }
}

// ═══════════════════════════════════════════════════════════
//  设置
// ═══════════════════════════════════════════════════════════

async function loadSettingsToForm() {
  const s = await API.getSettings();
  STATE.settings = s;

  document.getElementById('set-work').value = s.work_duration || 25;
  document.getElementById('set-short-break').value = s.short_break_duration || 5;
  document.getElementById('set-long-break').value = s.long_break_duration || 15;
  document.getElementById('set-before-long').value = s.pomodoros_before_long || 4;
  document.getElementById('set-daily-goal').value = (parseInt(s.daily_goal_minutes || 120) / 60).toFixed(1);

  // v3: 加载 lastTag
  STATE.lastTag = s.last_tag || '';

  // 主题
  document.documentElement.setAttribute('data-theme', s.theme || 'light');
  document.getElementById('theme-toggle').textContent = (s.theme === 'dark') ? '☀️' : '🌓';

  // 应用计时设置
  applyTimerSettings();

  // v3: 加载标签管理和数据路径
  renderTagManagement();
  loadDataPath();
}

async function saveSettings() {
  const btn = document.getElementById('btn-save-settings');
  btn.disabled = true;
  btn.textContent = '... 保存中 ...';

  try {
    const data = {
      work_duration: document.getElementById('set-work').value,
      short_break_duration: document.getElementById('set-short-break').value,
      long_break_duration: document.getElementById('set-long-break').value,
      pomodoros_before_long: document.getElementById('set-before-long').value,
      daily_goal_minutes: Math.round(parseFloat(document.getElementById('set-daily-goal').value) * 60),
      theme: STATE.settings.theme || 'light',
      last_tag: STATE.lastTag || '',
    };

    const result = await API.updateSettings(data);
    if (!result.ok) throw new Error('Server returned: ' + JSON.stringify(result));

    STATE.settings = { ...STATE.settings, ...data };
    applyTimerSettings();
    updateTimerDisplay();

    try { await updateDailyGoal(); } catch (e) { /* non-critical */ }

    alert('Settings saved!');
  } catch (err) {
    console.error('Save settings failed:', err);
    alert('Save failed: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存设置';
  }
}

function applyTimerSettings() {
  if (!STATE.isRunning) {
    STATE.timeLeft = getDurations()[STATE.mode];
    STATE.totalTime = STATE.timeLeft;
  }
}

// ═══════════════════════════════════════════════════════════
//  主题切换
// ═══════════════════════════════════════════════════════════

async function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  document.getElementById('theme-toggle').textContent = next === 'dark' ? '☀️' : '🌓';
  STATE.settings.theme = next;
  await API.updateSettings({ theme: next });

  // 重新渲染图表
  if (STATE.currentView === 'dashboard' && STATE.dashboardTab === 'trend') {
    setTimeout(renderTrendChart, 200);
  }
}

// ═══════════════════════════════════════════════════════════
//  导航
// ═══════════════════════════════════════════════════════════

function switchView(view) {
  STATE.currentView = view;

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + view).classList.add('active');

  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.nav-tab[data-view="${view}"]`).classList.add('active');

  if (view === 'dashboard') {
    // 默认热力图
    switchDashTab(STATE.dashboardTab);
  }
}

function switchDashTab(tab) {
  STATE.dashboardTab = tab;

  document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.dash-tab[data-dtab="${tab}"]`).classList.add('active');

  document.querySelectorAll('.dash-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('dash-' + tab).classList.add('active');

  if (tab === 'heatmap') renderHeatmap();
  if (tab === 'trend') setTimeout(renderTrendChart, 100); // 等 DOM 渲染完
  if (tab === 'cards') renderStatsCards();
}

// ═══════════════════════════════════════════════════════════
//  全部数据刷新
// ═══════════════════════════════════════════════════════════

async function refreshAllData() {
  await updateDailyGoal();
  await updateTagSuggestions();

  // 如果当前在看板，刷新对应面板
  if (STATE.currentView === 'dashboard') {
    if (STATE.dashboardTab === 'heatmap') renderHeatmap();
    if (STATE.dashboardTab === 'trend') renderTrendChart();
    if (STATE.dashboardTab === 'cards') renderStatsCards();
  }
}

// ═══════════════════════════════════════════════════════════
//  事件绑定
// ═══════════════════════════════════════════════════════════

function bindEvents() {
  // 导航
  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  // 主题切换
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

  // 计时器按钮
  document.getElementById('btn-start').addEventListener('click', startTimer);
  document.getElementById('btn-stop').addEventListener('click', stopTimer);
  document.getElementById('btn-skip').addEventListener('click', skipBreak);

  // 反思提交
  $('btn-reflection-submit').addEventListener('click', async () => {
    if (STATE.completedSession) {
      const activeStars = _dom.reflectionStars.querySelectorAll('.active').length;
      const input = _dom.reflectionInput.value.trim();
      _dom.reflectionModal.classList.remove('show');
      await handleReflectionSubmit({ focus_score: activeStars || null, reflection: input });
    }
  });
  $('btn-reflection-skip').addEventListener('click', async () => {
    if (STATE.completedSession) {
      _dom.reflectionModal.classList.remove('show');
      await handleReflectionSubmit({ focus_score: null, reflection: '' });
    }
  });

  // 看板子模块
  document.querySelectorAll('.dash-tab').forEach(btn => {
    btn.addEventListener('click', () => switchDashTab(btn.dataset.dtab));
  });

  // 标签筛选
  document.getElementById('dash-tag-filter').addEventListener('change', () => {
    if (STATE.dashboardTab === 'heatmap') renderHeatmap();
    if (STATE.dashboardTab === 'trend') renderTrendChart();
  });

  // v3: 标签明细时间范围筛选（按钮组）
  document.querySelectorAll('#tag-period-btns .tp-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#tag-period-btns .tp-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderTagBreakdown();
    });
  });

  // 热力图视图切换
  document.querySelectorAll('.hm-view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      STATE.hmView = btn.dataset.hm;
      document.querySelectorAll('.hm-view-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderHeatmap();
    });
  });

  // 热力图导航
  document.getElementById('hm-prev').addEventListener('click', () => {
    if (STATE.hmView === 'year') { STATE.hmYear--; }
    else {
      STATE.hmMonth--;
      if (STATE.hmMonth < 1) { STATE.hmMonth = 12; STATE.hmYear--; }
    }
    renderHeatmap();
  });
  document.getElementById('hm-next').addEventListener('click', () => {
    if (STATE.hmView === 'year') { STATE.hmYear++; }
    else {
      STATE.hmMonth++;
      if (STATE.hmMonth > 12) { STATE.hmMonth = 1; STATE.hmYear++; }
    }
    renderHeatmap();
  });

  // 趋势图粒度
  document.querySelectorAll('.trend-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      STATE.trendGran = btn.dataset.gran;
      document.querySelectorAll('.trend-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderTrendChart();
    });
  });

  // 设置保存
  document.getElementById('btn-save-settings').addEventListener('click', saveSettings);

  // v3: 标签新增按钮
  document.getElementById('btn-add-tag').addEventListener('click', () => showTagEditModal(null));

  // v3: 数据管理按钮
  document.getElementById('btn-export-json').addEventListener('click', () => API.exportData('json'));
  document.getElementById('btn-export-csv').addEventListener('click', () => API.exportData('csv'));
  document.getElementById('btn-backup').addEventListener('click', () => API.backup());
  document.getElementById('btn-copy-path').addEventListener('click', () => {
    const input = document.getElementById('data-path-display');
    input.select();
    navigator.clipboard.writeText(input.value).then(() => {
      const btn = document.getElementById('btn-copy-path');
      btn.textContent = '✓ 已复制';
      setTimeout(() => { btn.textContent = '📋 复制路径'; }, 2000);
    }).catch(() => alert('复制失败，请手动复制'));
  });
  document.getElementById('btn-open-folder').addEventListener('click', () => API.openDataFolder());

  // 窗口尺寸变化重新绘制图表
  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      if (STATE.currentView === 'dashboard' && STATE.dashboardTab === 'trend') {
        renderTrendChart();
      }
    }, 300);
  });
}

// ═══════════════════════════════════════════════════════════
//  初始化
// ═══════════════════════════════════════════════════════════

async function init() {
  // Populate DOM cache
  _dom = {
    timerText: $('timer-text'),
    timerMode: $('timer-mode'),
    timerPhase: $('timer-phase'),
    timerRing: $('timer-ring'),
    btnStart: $('btn-start'),
    btnStop: $('btn-stop'),
    btnSkip: $('btn-skip'),
    goalText: $('goal-text'),
    goalFill: $('goal-progress-fill'),
    goalPercent: $('goal-percent'),
    pomodoroCount: $('pomodoro-count'),
    todayCount: $('today-count'),
    // v3: 标签选择器
    tagChips: $('tag-chips'),
    activeTagDisplay: $('active-tag-display'),
    activeTagDot: $('active-tag-dot'),
    activeTagName: $('active-tag-name'),
    dashTagFilter: $('dash-tag-filter'),
    hmTitle: $('hm-title'),
    heatmapContainer: $('heatmap-container'),
    trendCanvas: $('trend-canvas'),
    reflectionModal: $('reflection-modal'),
    reflectionStars: $('reflection-stars'),
    reflectionInput: $('reflection-input'),
    confettiContainer: $('confetti-container'),
  };

  await loadSettingsToForm();
  await updateDailyGoal();
  await updateTagSuggestions();
  updateTimerDisplay();
  bindEvents();
  requestNotification();

  // 每 30 秒自动刷新看板数据（如果在看板页）
  setInterval(() => {
    if (STATE.currentView === 'dashboard') {
      if (STATE.dashboardTab === 'heatmap') renderHeatmap();
      if (STATE.dashboardTab === 'trend') renderTrendChart();
      if (STATE.dashboardTab === 'cards') renderStatsCards();
    }
    // 始终刷新目标进度
    updateDailyGoal();
  }, 30000);

  // 页面切回时立即同步计时器显示，避免后台节流导致的延迟
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && STATE.isRunning) {
      timerTick();
    }
  });

  console.log('🍅 番茄钟 v3 已就绪！');
}

document.addEventListener('DOMContentLoaded', init);

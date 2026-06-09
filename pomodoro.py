#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄钟 (Pomodoro Timer) — 桌面番茄工作法计时器
Python + tkinter，无额外依赖，双击即可运行
"""

import tkinter as tk
from tkinter import messagebox
import threading
import time
import winsound

# ── 常量配置 ──────────────────────────────────────────────

WORK_TIME = 25 * 60       # 工作时间：25 分钟
SHORT_BREAK = 5 * 60      # 短休息：5 分钟
LONG_BREAK = 15 * 60      # 长休息：15 分钟
POMODOROS_BEFORE_LONG = 4 # 4 个番茄后进入长休息

# 颜色主题（每种模式一套配色）
COLORS = {
    "work":        {"bg": "#FFF5F5", "accent": "#E74C3C", "light": "#FADBD8", "text": "#2C3E50", "btn_text": "#FFFFFF"},
    "short_break": {"bg": "#F0FFF0", "accent": "#27AE60", "light": "#D5F5E3", "text": "#2C3E50", "btn_text": "#FFFFFF"},
    "long_break":  {"bg": "#F0F4FF", "accent": "#2980B9", "light": "#D6EAF8", "text": "#2C3E50", "btn_text": "#FFFFFF"},
}

MODE_NAMES = {
    "work":        "🍅 专注工作中",
    "short_break": "☕ 短休息",
    "long_break":  "🌴 长休息",
}

FONT_TITLE  = ("Microsoft YaHei UI", 16, "bold")
FONT_TIMER  = ("Consolas", 48, "bold")
FONT_LABEL  = ("Microsoft YaHei UI", 12)
FONT_BUTTON = ("Microsoft YaHei UI", 11)
FONT_SMALL  = ("Microsoft YaHei UI", 10)


# ── 主应用类 ──────────────────────────────────────────────

class PomodoroApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🍅 番茄钟")
        self.root.geometry("420x560")
        self.root.resizable(False, False)

        # 设置应用图标（尝试）
        try:
            self.root.iconbitmap(default="tomato.ico")
        except Exception:
            pass

        # ── 状态变量 ──
        self.mode = "work"
        self.time_left = WORK_TIME
        self.total_time = WORK_TIME
        self.running = False
        self.pomodoro_count = 0
        self.after_id = None

        # 记录所有需要同步背景色的 widget
        self._bg_widgets = []

        # ── 构建界面 ──
        self._build_ui()

        # 窗口居中
        self.root.update_idletasks()
        w, h = 420, 560
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._update_display()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 辅助：创建带背景色的控件并登记 ──────────────────────

    def _frame(self, parent, **kw):
        """创建 Frame 并自动登记背景色"""
        f = tk.Frame(parent, **kw)
        self._bg_widgets.append(f)
        return f

    def _label(self, parent, **kw):
        """创建 Label 并自动登记背景色"""
        lbl = tk.Label(parent, **kw)
        self._bg_widgets.append(lbl)
        return lbl

    # ── 界面构建 ──────────────────────────────────────────

    def _build_ui(self):
        c = COLORS["work"]

        # 主容器
        self.main_frame = self._frame(self.root, bg=c["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # ── 标题 ──
        self.title_label = self._label(
            self.main_frame, text="🍅 番茄钟", font=FONT_TITLE,
            bg=c["bg"], fg=c["accent"]
        )
        self.title_label.pack(pady=(0, 15))

        # ── Canvas 进度圆环 + 计时数字 ──
        self.canvas_size = 280
        self.canvas = tk.Canvas(
            self.main_frame, width=self.canvas_size, height=self.canvas_size,
            bg=c["bg"], highlightthickness=0
        )
        self.canvas.pack()

        self.timer_text = self.canvas.create_text(
            self.canvas_size // 2, self.canvas_size // 2 - 15,
            text="25:00", font=FONT_TIMER, fill=c["text"]
        )

        self.mode_text = self.canvas.create_text(
            self.canvas_size // 2, self.canvas_size // 2 + 40,
            text="准备开始", font=FONT_LABEL, fill="#999999"
        )

        self.phase_text = self.canvas.create_text(
            self.canvas_size // 2, self.canvas_size // 2 + 65,
            text="", font=FONT_SMALL, fill="#AAAAAA"
        )

        self._draw_progress_ring()

        # ── 按钮行 ──
        self.btn_frame = self._frame(self.main_frame, bg=c["bg"])
        self.btn_frame.pack(pady=(20, 8))

        self.start_btn = tk.Button(
            self.btn_frame, text="▶  开始", font=FONT_BUTTON,
            bg=c["accent"], fg=c["btn_text"],
            activebackground="#C0392B", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=18, pady=8,
            cursor="hand2", command=self._toggle_timer
        )
        self.start_btn.pack(side=tk.LEFT, padx=4)

        self.reset_btn = tk.Button(
            self.btn_frame, text="↺  重置", font=FONT_BUTTON,
            bg="#BDC3C7", fg="#FFFFFF",
            activebackground="#95A5A6", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=18, pady=8,
            cursor="hand2", command=self._reset
        )
        self.reset_btn.pack(side=tk.LEFT, padx=4)

        self.skip_btn = tk.Button(
            self.btn_frame, text="⏭  跳过", font=FONT_BUTTON,
            bg="#BDC3C7", fg="#FFFFFF",
            activebackground="#95A5A6", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=18, pady=8,
            cursor="hand2", command=self._skip
        )
        self.skip_btn.pack(side=tk.LEFT, padx=4)

        # ── 统计信息 ──
        self.info_frame = self._frame(self.main_frame, bg=c["bg"])
        self.info_frame.pack(pady=(12, 5))

        self.count_label = self._label(
            self.info_frame, text="✅ 已完成: 0 个番茄", font=FONT_SMALL,
            bg=c["bg"], fg="#7F8C8D"
        )
        self.count_label.pack()

        # ── 底部选项 ──
        self.bottom_frame = self._frame(self.main_frame, bg=c["bg"])
        self.bottom_frame.pack(pady=(5, 0))

        self.topmost_var = tk.BooleanVar(value=False)
        topmost_cb = tk.Checkbutton(
            self.bottom_frame, text="📌 始终置顶", variable=self.topmost_var,
            font=FONT_SMALL, bg=c["bg"], fg="#7F8C8D",
            selectcolor=c["bg"], activebackground=c["bg"],
            cursor="hand2", command=self._toggle_topmost
        )
        topmost_cb.pack()
        self._bg_widgets.append(topmost_cb)

    # ── 进度圆环绘制 ──────────────────────────────────────

    def _draw_progress_ring(self, fraction=1.0):
        """绘制圆形进度条，fraction 为剩余比例 (0.0 ~ 1.0)"""
        self.canvas.delete("ring")

        cx = self.canvas_size // 2
        cy = self.canvas_size // 2
        r = 105
        width = 10

        c = COLORS[self.mode]

        # 背景圆环
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=c["light"], width=width, tags="ring"
        )

        if fraction <= 0:
            return

        # 前景弧线（从顶部 12 点顺时针绘制）
        angle = 360.0 * fraction
        self.canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=-angle,
            style=tk.ARC, outline=c["accent"], width=width, tags="ring"
        )

    # ── 计时引擎 ──────────────────────────────────────────

    def _toggle_timer(self):
        """开始 / 暂停切换"""
        if self.running:
            self._pause()
        else:
            self._start()

    def _start(self):
        self.running = True
        self.start_btn.config(text="⏸  暂停", bg="#E67E22")
        self.skip_btn.config(state=tk.DISABLED)
        self._tick()

    def _pause(self):
        self.running = False
        self.start_btn.config(text="▶  开始", bg=COLORS[self.mode]["accent"])
        self.skip_btn.config(state=tk.NORMAL)
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

    def _tick(self):
        """每秒回调"""
        if not self.running:
            return

        if self.time_left > 0:
            self.time_left -= 1
            self._update_display()
            self.after_id = self.root.after(1000, self._tick)
        else:
            self.running = False
            self._on_timer_end()

    def _on_timer_end(self):
        """计时结束处理"""
        self._update_display()

        if self.mode == "work":
            self.pomodoro_count += 1
            self._notify(
                "🍅 番茄完成！",
                f"太棒了！已完成 {self.pomodoro_count} 个番茄。\n休息一下吧~"
            )

            if self.pomodoro_count % POMODOROS_BEFORE_LONG == 0:
                self._switch_mode("long_break")
            else:
                self._switch_mode("short_break")
        else:
            name = {"short_break": "短休息", "long_break": "长休息"}.get(self.mode, "休息")
            self._notify("⏰ 休息结束！", f"{name}时间到，开始新的番茄吧！")
            self._switch_mode("work")

    # ── 模式切换 ──────────────────────────────────────────

    def _switch_mode(self, new_mode):
        self.mode = new_mode
        self.running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        times = {"work": WORK_TIME, "short_break": SHORT_BREAK, "long_break": LONG_BREAK}
        self.time_left = times[new_mode]
        self.total_time = times[new_mode]

        self.start_btn.config(text="▶  开始", bg=COLORS[self.mode]["accent"])
        self.skip_btn.config(state=tk.NORMAL)
        self._update_display()

    # ── 重置 ──────────────────────────────────────────────

    def _reset(self):
        self.running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        self.time_left = self.total_time
        self.start_btn.config(text="▶  开始", bg=COLORS[self.mode]["accent"])
        self.skip_btn.config(state=tk.NORMAL)
        self._update_display()

    # ── 跳过 ──────────────────────────────────────────────

    def _skip(self):
        if self.mode == "work":
            self._switch_mode("short_break")
        else:
            self._switch_mode("work")

    # ── 界面更新 ──────────────────────────────────────────

    def _update_display(self):
        """刷新倒计时数字、进度条、颜色等"""
        c = COLORS[self.mode]

        # ── 统一更新所有登记控件的背景色 ──
        self.root.configure(bg=c["bg"])
        for w in self._bg_widgets:
            try:
                w.configure(bg=c["bg"])
            except Exception:
                pass
        # Checkbutton 的 selectcolor 也要更新
        for child in self.bottom_frame.winfo_children():
            if isinstance(child, tk.Checkbutton):
                try:
                    child.configure(
                        bg=c["bg"],
                        selectcolor=c["bg"],
                        activebackground=c["bg"]
                    )
                except Exception:
                    pass

        # ── Canvas ──
        self.canvas.configure(bg=c["bg"])
        mins = self.time_left // 60
        secs = self.time_left % 60
        time_str = f"{mins:02d}:{secs:02d}"
        self.canvas.itemconfig(self.timer_text, text=time_str, fill=c["text"])

        mode_label = MODE_NAMES.get(self.mode, "")
        self.canvas.itemconfig(self.mode_text, text=mode_label, fill=c["accent"])

        # 阶段提示
        long_after = POMODOROS_BEFORE_LONG - (self.pomodoro_count % POMODOROS_BEFORE_LONG)
        if self.mode == "work":
            phase = f"第 {self.pomodoro_count + 1} 个番茄 | {long_after} 个后长休息"
        else:
            phase = f"已完成 {self.pomodoro_count} 个番茄"
        self.canvas.itemconfig(self.phase_text, text=phase)

        # ── 进度圆环 ──
        fraction = self.time_left / self.total_time if self.total_time > 0 else 0
        self._draw_progress_ring(fraction)

        # ── 统计标签 ──
        self.count_label.config(
            text=f"✅ 已完成: {self.pomodoro_count} 个番茄",
            fg="#7F8C8D"
        )

        # ── 标题 ──
        self.title_label.config(fg=c["accent"])

        # ── 按钮 ──
        if not self.running:
            self.start_btn.config(bg=c["accent"], fg=c["btn_text"])

    # ── 通知 ──────────────────────────────────────────────

    def _notify(self, title, message):
        """Windows 通知：声音（后台线程） + 弹窗（延迟，避免阻塞 UI）"""
        threading.Thread(target=self._play_sound, daemon=True).start()
        # 延迟弹出，让 UI 先刷新
        self.root.after(300, lambda: self._show_toast(title, message))

    def _play_sound(self):
        """播放完成音效（三声短促系统提示音）"""
        for _ in range(3):
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            time.sleep(0.3)

    def _show_toast(self, title, message):
        """弹窗提醒 + 窗口短暂置顶闪烁"""
        self.root.bell()
        old_topmost = self.topmost_var.get()
        self.root.attributes('-topmost', True)
        self.root.lift()
        self.root.after(1000, lambda: self.root.attributes('-topmost', old_topmost))
        self.root.after(600, lambda: messagebox.showinfo(title, message))

    # ── 置顶切换 ──────────────────────────────────────────

    def _toggle_topmost(self):
        self.root.attributes('-topmost', self.topmost_var.get())

    # ── 关闭 ──────────────────────────────────────────────

    def _on_close(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.root.destroy()

    # ── 启动 ──────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ── 入口 ──────────────────────────────────────────────────

if __name__ == "__main__":
    app = PomodoroApp()
    app.run()

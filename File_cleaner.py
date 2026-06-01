#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
递归文件删除工具 - File Cleaner Pro
支持高分辨率显示器 (2K/4K/HiDPI)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import pathlib
import threading
from datetime import datetime
import platform


# ─── 颜色主题 ────────────────────────────────────────────────
COLORS = {
    "bg":           "#0D1117",
    "surface":      "#161B22",
    "surface2":     "#1C2128",
    "border":       "#30363D",
    "border_focus": "#58A6FF",
    "accent":       "#238636",
    "accent_hover": "#2EA043",
    "danger":       "#DA3633",
    "danger_hover": "#F85149",
    "warning":      "#E3B341",
    "text":         "#E6EDF3",
    "text_muted":   "#8B949E",
    "text_dim":     "#484F58",
    "tag_bg":       "#21262D",
    "tag_border":   "#388BFD",
    "tag_text":     "#79C0FF",
    "success":      "#3FB950",
    "log_add":      "#3FB950",
    "log_del":      "#F85149",
    "log_info":     "#58A6FF",
    "log_warn":     "#E3B341",
}

# ─── DPI 感知缩放 ─────────────────────────────────────────────
def get_scale_factor():
    """根据屏幕 DPI 计算缩放比例，适配 2K/4K 显示器"""
    try:
        import ctypes
        if platform.system() == "Windows":
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            dpi = ctypes.windll.user32.GetDpiForSystem()
            return dpi / 96.0
    except Exception:
        pass
    return 1.0

SCALE = get_scale_factor()

def s(v):
    """缩放整数值"""
    return max(1, int(v * SCALE))

def sf(v):
    """缩放字体大小"""
    return max(8, int(v * SCALE))


# ─── 圆角画布按钮 ─────────────────────────────────────────────
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg=COLORS["accent"],
                 hover_bg=COLORS["accent_hover"], fg=COLORS["text"],
                 width=120, height=36, radius=8, font_size=10, **kwargs):
        super().__init__(parent, width=s(width), height=s(height),
                         bg=COLORS["bg"], highlightthickness=0, **kwargs)
        self._text = text
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._radius = s(radius)
        self._btn_width = s(width)    # 原先 self._w
        self._btn_height = s(height)  # 原先 self._h
        self._font_size = sf(font_size)
        self._draw(bg)
        self.bind("<Enter>", lambda e: self._draw(hover_bg))
        self.bind("<Leave>", lambda e: self._draw(bg))
        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", lambda e: self._draw(hover_bg))

    def _draw(self, color):
        self.delete("all")
        r = self._radius
        w, h = self._btn_width, self._btn_height
        # 圆角矩形
        self.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=color, outline=color)
        self.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=color, outline=color)
        self.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=color, outline=color)
        self.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=color, outline=color)
        self.create_rectangle(r, 0, w-r, h, fill=color, outline=color)
        self.create_rectangle(0, r, w, h-r, fill=color, outline=color)
        self.create_text(w//2, h//2, text=self._text, fill=self._fg,
                         font=("Helvetica", self._font_size, "bold"))

    def _on_click(self, e):
        self._draw(self._bg)
        if self._command:
            self._command()

    def set_state(self, state):
        """disabled / normal"""
        if state == "disabled":
            self._bg_orig = self._bg
            self._bg = COLORS["text_dim"]
            self._hover_bg_orig = self._hover_bg
            self._hover_bg = COLORS["text_dim"]
            self._draw(COLORS["text_dim"])
            self.unbind("<Button-1>")
            self.unbind("<Enter>")
            self.unbind("<Leave>")
        else:
            self._bg = getattr(self, "_bg_orig", self._bg)
            self._hover_bg = getattr(self, "_hover_bg_orig", self._hover_bg)
            self._draw(self._bg)
            self.bind("<Enter>", lambda e: self._draw(self._hover_bg))
            self.bind("<Leave>", lambda e: self._draw(self._bg))
            self.bind("<Button-1>", self._on_click)


# ─── 文件标签组件 ──────────────────────────────────────────────
class FileTag(tk.Frame):
    def __init__(self, parent, filename, on_remove, **kwargs):
        super().__init__(parent, bg=COLORS["tag_bg"],
                         highlightthickness=1,
                         highlightbackground=COLORS["tag_border"],
                         **kwargs)
        self.filename = filename
        lbl = tk.Label(self, text=filename, bg=COLORS["tag_bg"],
                       fg=COLORS["tag_text"],
                       font=("Courier", sf(9), "bold"),
                       padx=s(6), pady=s(3))
        lbl.pack(side="left")
        btn = tk.Label(self, text="×", bg=COLORS["tag_bg"],
                       fg=COLORS["text_muted"],
                       font=("Helvetica", sf(11), "bold"),
                       cursor="hand2", padx=s(4))
        btn.pack(side="left")
        btn.bind("<Button-1>", lambda e: on_remove(self))
        btn.bind("<Enter>", lambda e: btn.config(fg=COLORS["danger"]))
        btn.bind("<Leave>", lambda e: btn.config(fg=COLORS["text_muted"]))


# ─── 主应用 ───────────────────────────────────────────────────
class FileCleanerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("File Cleaner Pro  ·  递归文件删除工具")
        self.configure(bg=COLORS["bg"])
        self.minsize(s(640), s(520))

        # DPI 感知
        try:
            self.tk.call("tk", "scaling", SCALE * 1.333)
        except Exception:
            pass

        self._target_dir = tk.StringVar()
        self._file_tags = []      # FileTag 列表
        self._scan_results = []   # 扫描到的文件路径列表
        self._running = False

        self._build_ui()
        self._center_window(900, 680)

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - s(w)) // 2
        y = (sh - s(h)) // 2
        self.geometry(f"{s(w)}x{s(h)}+{x}+{y}")

    # ── 构建整体 UI ──────────────────────────────────────────
    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self, bg=COLORS["surface"], height=s(52))
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="⌫", bg=COLORS["surface"], fg=COLORS["danger"],
                 font=("Helvetica", sf(22))).pack(side="left", padx=s(18))
        tk.Label(header, text="File Cleaner Pro",
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=("Georgia", sf(15), "bold")).pack(side="left")
        tk.Label(header, text="递归文件删除工具",
                 bg=COLORS["surface"], fg=COLORS["text_muted"],
                 font=("Helvetica", sf(10))).pack(side="left", padx=s(10))

        sep = tk.Frame(self, bg=COLORS["border"], height=1)
        sep.pack(fill="x")

        # 主内容区（左右分栏，响应式）
        main = tk.Frame(self, bg=COLORS["bg"])
        main.pack(fill="both", expand=True, padx=s(20), pady=s(16))

        # 左侧控制面板
        left = tk.Frame(main, bg=COLORS["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, s(10)))
        self._build_left(left)

        # 右侧日志面板
        right = tk.Frame(main, bg=COLORS["surface"], width=s(300),
                         highlightthickness=1,
                         highlightbackground=COLORS["border"])
        right.pack(side="right", fill="both", expand=False)
        right.pack_propagate(False)
        self._build_log(right)

    # ── 左侧面板 ─────────────────────────────────────────────
    def _build_left(self, parent):
        # ① 目标文件夹
        self._section(parent, "① 目标文件夹")
        dir_row = tk.Frame(parent, bg=COLORS["bg"])
        dir_row.pack(fill="x", pady=(s(4), s(12)))

        entry_frame = tk.Frame(dir_row, bg=COLORS["surface"],
                               highlightthickness=1,
                               highlightbackground=COLORS["border"])
        entry_frame.pack(side="left", fill="x", expand=True, padx=(0, s(8)))
        self._dir_entry = tk.Entry(entry_frame,
                                   textvariable=self._target_dir,
                                   bg=COLORS["surface"], fg=COLORS["text"],
                                   insertbackground=COLORS["text"],
                                   relief="flat", font=("Courier", sf(10)),
                                   bd=s(6))
        self._dir_entry.pack(fill="x")
        self._dir_entry.bind("<FocusIn>",
            lambda e: entry_frame.config(highlightbackground=COLORS["border_focus"]))
        self._dir_entry.bind("<FocusOut>",
            lambda e: entry_frame.config(highlightbackground=COLORS["border"]))

        RoundedButton(dir_row, "浏览", command=self._browse_dir,
                      width=72, height=32, font_size=9).pack(side="left")

        # ② 要删除的文件名
        self._section(parent, "② 指定要删除的文件名（支持多个）")

        # 输入行
        add_row = tk.Frame(parent, bg=COLORS["bg"])
        add_row.pack(fill="x", pady=(s(4), s(6)))

        self._filename_var = tk.StringVar()
        input_frame = tk.Frame(add_row, bg=COLORS["surface"],
                               highlightthickness=1,
                               highlightbackground=COLORS["border"])
        input_frame.pack(side="left", fill="x", expand=True, padx=(0, s(8)))
        self._filename_entry = tk.Entry(input_frame,
                                        textvariable=self._filename_var,
                                        bg=COLORS["surface"], fg=COLORS["text"],
                                        insertbackground=COLORS["text"],
                                        relief="flat", font=("Courier", sf(10)),
                                        bd=s(6))
        self._filename_entry.pack(fill="x")
        self._filename_entry.bind("<Return>", lambda e: self._add_filename())
        self._filename_entry.bind("<FocusIn>",
            lambda e: input_frame.config(highlightbackground=COLORS["border_focus"]))
        self._filename_entry.bind("<FocusOut>",
            lambda e: input_frame.config(highlightbackground=COLORS["border"]))

        placeholder = tk.Label(add_row, text="支持通配符，如 *.tmp",
                                bg=COLORS["bg"], fg=COLORS["text_dim"],
                                font=("Helvetica", sf(8)))
        # 不放这里，放 hint

        RoundedButton(add_row, "+ 添加", command=self._add_filename,
                      width=72, height=32, font_size=9).pack(side="left")

        tk.Label(parent, text="支持精确文件名（如 .DS_Store）或通配符（如 *.log、Thumbs.*）",
                 bg=COLORS["bg"], fg=COLORS["text_dim"],
                 font=("Helvetica", sf(8))).pack(anchor="w", pady=(0, s(6)))

        # 标签容器（可滚动）
        tag_outer = tk.Frame(parent, bg=COLORS["surface"],
                             highlightthickness=1,
                             highlightbackground=COLORS["border"])
        tag_outer.pack(fill="x", pady=(0, s(12)))

        self._tag_canvas = tk.Canvas(tag_outer, bg=COLORS["surface"],
                                     highlightthickness=0,
                                     height=s(76))
        self._tag_canvas.pack(fill="both", padx=s(6), pady=s(6))
        self._tag_frame = tk.Frame(self._tag_canvas, bg=COLORS["surface"])
        self._tag_window = self._tag_canvas.create_window(
            0, 0, anchor="nw", window=self._tag_frame)
        self._tag_canvas.bind("<Configure>", self._on_canvas_configure)
        self._tag_frame.bind("<Configure>", self._on_frame_configure)

        self._empty_label = tk.Label(self._tag_canvas,
                                     text="尚未添加任何文件名 ·  请在上方输入后点击「+ 添加」",
                                     bg=COLORS["surface"], fg=COLORS["text_dim"],
                                     font=("Helvetica", sf(9)))
        self._empty_label.place(relx=0.5, rely=0.5, anchor="center")

        # ③ 选项
        self._section(parent, "③ 选项")
        opts = tk.Frame(parent, bg=COLORS["bg"])
        opts.pack(fill="x", pady=(s(4), s(12)))

        self._dry_run = tk.BooleanVar(value=True)
        self._confirm_var = tk.BooleanVar(value=True)

        self._check(opts, "模拟运行（不实际删除，仅预览）", self._dry_run)
        self._check(opts, "删除前二次确认", self._confirm_var)

        # ④ 操作按钮
        btn_row = tk.Frame(parent, bg=COLORS["bg"])
        btn_row.pack(fill="x", pady=(s(4), 0))

        self._scan_btn = RoundedButton(btn_row, "🔍 扫描预览",
                                       command=self._start_scan,
                                       bg=COLORS["border_focus"],
                                       hover_bg="#4493F8",
                                       width=120, height=38, font_size=10)
        self._scan_btn.pack(side="left", padx=(0, s(10)))

        self._delete_btn = RoundedButton(btn_row, "🗑 执行删除",
                                         command=self._start_delete,
                                         bg=COLORS["danger"],
                                         hover_bg=COLORS["danger_hover"],
                                         width=120, height=38, font_size=10)
        self._delete_btn.pack(side="left", padx=(0, s(10)))
        self._delete_btn.set_state("disabled")

        RoundedButton(btn_row, "清空日志",
                      command=self._clear_log,
                      bg=COLORS["surface2"],
                      hover_bg=COLORS["border"],
                      width=88, height=38, font_size=9).pack(side="left")

        # 进度条
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.Horizontal.TProgressbar",
                        troughcolor=COLORS["surface2"],
                        background=COLORS["accent"],
                        borderwidth=0, relief="flat")
        self._progress = ttk.Progressbar(parent, style="Dark.Horizontal.TProgressbar",
                                          mode="indeterminate",
                                          length=s(400))
        self._progress.pack(fill="x", pady=(s(10), 0))

        # 状态栏
        self._status_var = tk.StringVar(value="就绪  ·  请先选择目录并添加要删除的文件名")
        tk.Label(parent, textvariable=self._status_var,
                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Helvetica", sf(9)),
                 anchor="w").pack(fill="x", pady=(s(6), 0))

    # ── 右侧日志 ──────────────────────────────────────────────
    def _build_log(self, parent):
        header = tk.Frame(parent, bg=COLORS["surface2"], height=s(36))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="执行日志", bg=COLORS["surface2"],
                 fg=COLORS["text"], font=("Helvetica", sf(10), "bold"),
                 padx=s(12)).pack(side="left", fill="y")
        self._log_count = tk.StringVar(value="0 条")
        tk.Label(header, textvariable=self._log_count,
                 bg=COLORS["surface2"], fg=COLORS["text_muted"],
                 font=("Courier", sf(8)), padx=s(8)).pack(side="right", fill="y")

        sep = tk.Frame(parent, bg=COLORS["border"], height=1)
        sep.pack(fill="x")

        log_frame = tk.Frame(parent, bg=COLORS["surface"])
        log_frame.pack(fill="both", expand=True, padx=s(1))

        self._log_text = tk.Text(log_frame, bg=COLORS["surface"],
                                  fg=COLORS["text"], relief="flat",
                                  font=("Courier", sf(8)),
                                  wrap="word", state="disabled",
                                  padx=s(8), pady=s(6),
                                  selectbackground=COLORS["surface2"],
                                  insertbackground=COLORS["text"])
        scrollbar = tk.Scrollbar(log_frame, orient="vertical",
                                  command=self._log_text.yview,
                                  bg=COLORS["surface2"],
                                  troughcolor=COLORS["surface"],
                                  width=s(10))
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.tag_config("del", foreground=COLORS["log_del"])
        self._log_text.tag_config("add", foreground=COLORS["log_add"])
        self._log_text.tag_config("info", foreground=COLORS["log_info"])
        self._log_text.tag_config("warn", foreground=COLORS["log_warn"])
        self._log_text.tag_config("dim", foreground=COLORS["text_muted"])
        scrollbar.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True)
        self._log_line_count = 0

    # ── 辅助 UI 组件 ─────────────────────────────────────────
    def _section(self, parent, text):
        f = tk.Frame(parent, bg=COLORS["bg"])
        f.pack(fill="x", pady=(s(8), s(2)))
        tk.Label(f, text=text, bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Helvetica", sf(9), "bold")).pack(side="left")
        tk.Frame(f, bg=COLORS["border"], height=1).pack(
            side="left", fill="x", expand=True, padx=(s(8), 0))

    def _check(self, parent, text, var):
        f = tk.Frame(parent, bg=COLORS["bg"], cursor="hand2")
        f.pack(anchor="w", pady=s(2))
        cb = tk.Checkbutton(f, variable=var, bg=COLORS["bg"],
                             fg=COLORS["text"], selectcolor=COLORS["surface2"],
                             activebackground=COLORS["bg"],
                             activeforeground=COLORS["text"],
                             font=("Helvetica", sf(9)))
        cb.pack(side="left")
        tk.Label(f, text=text, bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Helvetica", sf(9))).pack(side="left")
        f.bind("<Button-1>", lambda e: var.set(not var.get()))

    # ── 标签 canvas 响应 ──────────────────────────────────────
    def _on_canvas_configure(self, e):
        self._tag_canvas.itemconfig(self._tag_window, width=e.width)

    def _on_frame_configure(self, e):
        self._tag_canvas.configure(scrollregion=self._tag_canvas.bbox("all"))

    # ── 动作 ─────────────────────────────────────────────────
    def _browse_dir(self):
        d = filedialog.askdirectory(title="选择目标文件夹")
        if d:
            self._target_dir.set(d)
            self._log(f"已选择目录: {d}", "info")

    def _add_filename(self):
        raw = self._filename_var.get().strip()
        if not raw:
            return
        # 支持逗号/空格分隔批量添加
        names = [n.strip() for n in raw.replace(",", " ").split() if n.strip()]
        for name in names:
            if any(t.filename == name for t in self._file_tags):
                self._log(f"「{name}」已存在，跳过", "warn")
                continue
            tag = FileTag(self._tag_frame, name, self._remove_tag)
            tag.pack(side="left", padx=s(4), pady=s(4))
            self._file_tags.append(tag)
            self._log(f"已添加目标文件名: {name}", "add")
        self._filename_var.set("")
        self._update_empty_label()
        self._delete_btn.set_state("disabled")
        self._scan_results.clear()

    def _remove_tag(self, tag):
        self._log(f"已移除: {tag.filename}", "dim")
        self._file_tags.remove(tag)
        tag.destroy()
        self._update_empty_label()
        self._delete_btn.set_state("disabled")
        self._scan_results.clear()

    def _update_empty_label(self):
        if self._file_tags:
            self._empty_label.place_forget()
        else:
            self._empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _validate_inputs(self):
        if not self._target_dir.get().strip():
            messagebox.showwarning("提示", "请先选择目标文件夹！")
            return False
        if not os.path.isdir(self._target_dir.get().strip()):
            messagebox.showerror("错误", "所选路径不是有效目录！")
            return False
        if not self._file_tags:
            messagebox.showwarning("提示", "请至少添加一个要删除的文件名！")
            return False
        return True

    # ── 扫描 ─────────────────────────────────────────────────
    def _start_scan(self):
        if not self._validate_inputs() or self._running:
            return
        self._running = True
        self._scan_results.clear()
        self._delete_btn.set_state("disabled")
        self._progress.start(12)
        self._status_var.set("正在扫描目录树…")
        self._log("─" * 36, "dim")
        self._log(f"开始扫描: {self._target_dir.get()}", "info")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        import fnmatch
        root = self._target_dir.get().strip()
        patterns = [t.filename for t in self._file_tags]
        found = []
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                for fname in filenames:
                    for pat in patterns:
                        if fnmatch.fnmatch(fname, pat):
                            found.append(os.path.join(dirpath, fname))
                            break
        except PermissionError as e:
            self.after(0, self._log, f"权限错误: {e}", "warn")

        self.after(0, self._scan_done, found)

    def _scan_done(self, found):
        self._running = False
        self._progress.stop()
        self._scan_results = found
        self._log(f"扫描完成，共找到 {len(found)} 个匹配文件", "info")
        if found:
            for f in found:
                self._log(f"  · {f}", "warn")
            self._delete_btn.set_state("normal")
            self._status_var.set(f"扫描完成 · 找到 {len(found)} 个文件，可执行删除")
        else:
            self._status_var.set("扫描完成 · 未找到匹配文件")
        self._log("─" * 36, "dim")

    # ── 删除 ─────────────────────────────────────────────────
    def _start_delete(self):
        if not self._scan_results or self._running:
            return
        dry = self._dry_run.get()
        mode = "【模拟运行】" if dry else "【真实删除】"
        if self._confirm_var.get():
            msg = (f"{mode}\n\n即将删除 {len(self._scan_results)} 个文件。\n\n"
                   f"{'（模拟模式下不会实际删除文件）' if dry else '⚠️ 此操作不可撤销！'}\n\n确认继续？")
            if not messagebox.askyesno("确认", msg, icon="warning"):
                return
        self._running = True
        self._progress.start(12)
        self._status_var.set(f"{mode} 正在处理…")
        self._log(f"{mode} 开始删除操作", "info")
        threading.Thread(target=self._delete_worker,
                         args=(list(self._scan_results), dry), daemon=True).start()

    def _delete_worker(self, files, dry):
        success, fail = 0, 0
        for fpath in files:
            try:
                if not dry:
                    os.remove(fpath)
                self.after(0, self._log, f"{'[模拟] ' if dry else '[删除] '}{fpath}",
                           "dim" if dry else "del")
                success += 1
            except Exception as e:
                self.after(0, self._log, f"[失败] {fpath}  ← {e}", "warn")
                fail += 1
        self.after(0, self._delete_done, success, fail, dry)

    def _delete_done(self, success, fail, dry):
        self._running = False
        self._progress.stop()
        mode = "模拟" if dry else "删除"
        self._log(f"{mode}完成：成功 {success} 个，失败 {fail} 个", "add")
        self._log("─" * 36, "dim")
        self._status_var.set(
            f"{mode}完成 · 成功 {success} 个 · 失败 {fail} 个")
        if not dry:
            self._scan_results.clear()
            self._delete_btn.set_state("disabled")

    # ── 日志 ─────────────────────────────────────────────────
    def _log(self, msg, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"{ts}  {msg}\n", tag or "")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")
        self._log_line_count += 1
        self._log_count.set(f"{self._log_line_count} 条")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._log_line_count = 0
        self._log_count.set("0 条")


# ─── 入口 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    app = FileCleanerApp()
    app.mainloop()
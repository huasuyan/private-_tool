"""
目录结构复制工具 - GUI 版本
依赖：Python 标准库（tkinter 已内置，无需额外安装）
运行：python copy_structure_gui.py
"""

import os
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 支持的图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.svg'}


# ── 核心逻辑（与原脚本相同）────────────────────────────────────────────

def get_first_image(folder: Path):
    images = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
    )
    return images[0] if images else None


def copy_structure(src: Path, dst: Path, log_callback, progress_callback):
    """递归复制目录结构，回调用于更新 GUI 日志和进度条。"""
    # 先统计总文件夹数，用于进度条
    all_dirs = [r for r, _, _ in os.walk(src)]
    total = len(all_dirs)
    stats = {'folders_created': 0, 'images_copied': 0, 'folders_skipped': 0}

    for idx, (root, dirs, _) in enumerate(os.walk(src), 1):
        root_path = Path(root)
        relative = root_path.relative_to(src)
        target_dir = dst / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        stats['folders_created'] += 1

        label = str(relative) if str(relative) != '.' else '（根目录）'
        first_image = get_first_image(root_path)

        if first_image:
            shutil.copy2(first_image, target_dir / first_image.name)
            stats['images_copied'] += 1
            log_callback(f"✔  {label}  →  {first_image.name}", 'ok')
        else:
            stats['folders_skipped'] += 1
            log_callback(f"—  {label}  （无图片）", 'skip')

        progress_callback(idx, total)
        dirs.sort()

    return stats


# ── GUI ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("目录结构复制工具")
        self.resizable(True, True)
        self.minsize(620, 520)
        self._build_ui()
        self._center_window(700, 580)

    def _center_window(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── 构建界面 ──────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {'padx': 16, 'pady': 6}

        # ── 路径选择区域 ──
        frame_paths = ttk.LabelFrame(self, text="路径设置", padding=10)
        frame_paths.pack(fill='x', **pad)
        frame_paths.columnconfigure(1, weight=1)

        # 源目录
        ttk.Label(frame_paths, text="源目录：").grid(row=0, column=0, sticky='w', pady=4)
        self.src_var = tk.StringVar()
        ttk.Entry(frame_paths, textvariable=self.src_var).grid(row=0, column=1, sticky='ew', padx=8)
        ttk.Button(frame_paths, text="浏览…", width=7,
                   command=lambda: self._browse(self.src_var)).grid(row=0, column=2)

        # 目标目录
        ttk.Label(frame_paths, text="目标目录：").grid(row=1, column=0, sticky='w', pady=4)
        self.dst_var = tk.StringVar()
        ttk.Entry(frame_paths, textvariable=self.dst_var).grid(row=1, column=1, sticky='ew', padx=8)
        ttk.Button(frame_paths, text="浏览…", width=7,
                   command=lambda: self._browse(self.dst_var)).grid(row=1, column=2)

        # ── 操作按钮 ──
        frame_btns = ttk.Frame(self)
        frame_btns.pack(fill='x', padx=16, pady=(0, 4))

        self.run_btn = ttk.Button(frame_btns, text="▶  开始复制", command=self._start)
        self.run_btn.pack(side='left')
        ttk.Button(frame_btns, text="清空日志", command=self._clear_log).pack(side='left', padx=8)

        # ── 进度条 ──
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress.pack(fill='x', padx=16, pady=(0, 4))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var,
                  foreground='gray').pack(anchor='w', padx=16)

        # ── 日志区域 ──
        frame_log = ttk.LabelFrame(self, text="运行日志", padding=6)
        frame_log.pack(fill='both', expand=True, padx=16, pady=(4, 16))

        self.log = tk.Text(frame_log, state='disabled', wrap='none',
                           font=('Consolas', 10), relief='flat', bd=0)
        self.log.pack(side='left', fill='both', expand=True)

        sb = ttk.Scrollbar(frame_log, command=self.log.yview)
        sb.pack(side='right', fill='y')
        self.log['yscrollcommand'] = sb.set

        # 日志颜色标签
        self.log.tag_config('ok',    foreground='#2e7d32')
        self.log.tag_config('skip',  foreground='#888888')
        self.log.tag_config('info',  foreground='#1565c0')
        self.log.tag_config('error', foreground='#c62828')
        self.log.tag_config('bold',  font=('Consolas', 10, 'bold'))

    # ── 事件处理 ─────────────────────────────────────────────────────

    def _browse(self, var: tk.StringVar):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            var.set(path)

    def _clear_log(self):
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')
        self.progress_var.set(0)
        self.status_var.set("就绪")

    def _start(self):
        src_str = self.src_var.get().strip()
        dst_str = self.dst_var.get().strip()

        if not src_str or not dst_str:
            messagebox.showwarning("缺少路径", "请先选择源目录和目标目录。")
            return

        src = Path(src_str)
        dst = Path(dst_str)

        if not src.exists() or not src.is_dir():
            messagebox.showerror("错误", f"源目录不存在或不是文件夹：\n{src}")
            return

        if dst.exists() and dst.is_dir() and any(dst.iterdir()):
            if not messagebox.askyesno("目标目录非空",
                                       f"目标目录已存在且包含文件：\n{dst}\n\n同名文件将被覆盖，是否继续？"):
                return

        self.run_btn.config(state='disabled')
        self._clear_log()
        self._log(f"源目录：  {src}", 'info')
        self._log(f"目标目录：{dst}", 'info')
        self._log("─" * 60, 'info')

        # 在子线程中运行，避免阻塞 GUI
        threading.Thread(target=self._run, args=(src, dst), daemon=True).start()

    def _run(self, src: Path, dst: Path):
        try:
            stats = copy_structure(src, dst, self._log, self._update_progress)
            self._log("─" * 60, 'info')
            self._log(f"完成！创建文件夹 {stats['folders_created']} 个，"
                      f"复制图片 {stats['images_copied']} 张，"
                      f"无图片文件夹 {stats['folders_skipped']} 个。", 'bold')
            self.after(0, lambda: self.status_var.set(
                f"完成  ·  {stats['folders_created']} 个文件夹  ·  {stats['images_copied']} 张图片"))
        except Exception as e:
            self._log(f"出错：{e}", 'error')
            self.after(0, lambda: self.status_var.set("出错，请查看日志"))
        finally:
            self.after(0, lambda: self.run_btn.config(state='normal'))

    # ── 回调 ─────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = ''):
        def _append():
            self.log.config(state='normal')
            self.log.insert('end', msg + '\n', tag)
            self.log.see('end')
            self.log.config(state='disabled')
        self.after(0, _append)

    def _update_progress(self, current: int, total: int):
        pct = current / total * 100 if total else 100
        self.after(0, lambda: self.progress_var.set(pct))
        self.after(0, lambda: self.status_var.set(f"处理中… {current} / {total}"))


# ── 入口 ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = App()
    app.mainloop()
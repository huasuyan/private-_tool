"""
WebP动画转视频工具 (WebP Animated → MP4/AVI/MOV)
依赖: pip install pillow
需要系统安装 ffmpeg (https://ffmpeg.org)

用法:
  python webp_to_video.py                  # 打开图形界面
  python webp_to_video.py /path/to/folder  # 命令行模式
"""

import os
import sys
import struct
import subprocess
import tempfile
import shutil
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image


# ──────────────────────────────────────────────
# 核心逻辑
# ──────────────────────────────────────────────

def parse_webp_frames(path: str) -> list[tuple["Image.Image", int]]:
    """
    返回 [(PIL.Image, duration_ms), ...] 列表。
    duration 从 ANMF 二进制块直接读取，保证准确。
    静态 WebP 返回 [(image, 100)] 单帧。
    """
    with open(path, "rb") as f:
        data = f.read()

    img = Image.open(path)

    # 静态 webp
    if not hasattr(img, "n_frames") or img.n_frames == 1:
        img.seek(0)
        return [(img.convert("RGBA"), 100)]

    # 从 ANMF 块解析每帧 duration
    durations = []
    for m in re.finditer(b"ANMF", data):
        pos = m.start() + 8  # 跳过 FourCC + size(4)
        dur = struct.unpack_from("<I", data, pos + 12)[0] & 0xFFFFFF
        durations.append(max(dur, 1))  # 至少 1ms，防止除零

    frames = []
    for i in range(img.n_frames):
        img.seek(i)
        frame = img.copy().convert("RGBA")
        dur = durations[i] if i < len(durations) else 100
        frames.append((frame, dur))

    return frames


def composite_on_bg(frame: "Image.Image", bg_color=(0, 0, 0)) -> "Image.Image":
    """将 RGBA 帧合成到纯色背景（用于编码 mp4 时去掉 alpha）。"""
    bg = Image.new("RGB", frame.size, bg_color)
    bg.paste(frame, mask=frame.split()[3])
    return bg


def get_video_size(frames: list) -> tuple[int, int]:
    """获取所有文件中最大尺寸，作为视频分辨率（自动 pad 小尺寸帧）。"""
    max_w = max_h = 0
    for img, _ in frames:
        max_w = max(max_w, img.width)
        max_h = max(max_h, img.height)
    # 确保宽高为偶数（H.264 要求）
    max_w += max_w % 2
    max_h += max_h % 2
    return max_w, max_h


def pad_frame(img: "Image.Image", target_w: int, target_h: int) -> "Image.Image":
    """在右侧/底部补黑边到目标尺寸。"""
    if img.width == target_w and img.height == target_h:
        return img
    bg = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    bg.paste(img, (0, 0))
    return bg


def convert_webps_to_video(
    webp_files: list[str],
    output_path: str,
    codec: str = "libx264",
    crf: int = 18,
    progress_cb=None,
    log_cb=None,
):
    """
    把多个动态 WebP 拼接成视频。

    webp_files  : 已排序的文件路径列表
    output_path : 输出视频路径（.mp4/.avi/.mov）
    codec       : ffmpeg 视频编码器
    crf         : 质量参数（0最优，51最差，18-23常用）
    progress_cb : 回调 progress_cb(current, total)
    log_cb      : 回调 log_cb(message)
    """

    def log(msg):
        if log_cb:
            log_cb(msg)
        else:
            print(msg)

    total_files = len(webp_files)
    log(f"共 {total_files} 个文件，开始解析...")

    # ── 第一遍：收集所有帧，确定统一分辨率 ──
    all_frames: list[tuple["Image.Image", int]] = []
    for i, path in enumerate(webp_files):
        try:
            frames = parse_webp_frames(path)
            all_frames.extend(frames)
            log(f"[{i+1}/{total_files}] {Path(path).name}  ({len(frames)} 帧)")
        except Exception as e:
            log(f"[警告] 跳过 {Path(path).name}: {e}")
        if progress_cb:
            progress_cb(i + 1, total_files * 2)  # 前半进度

    if not all_frames:
        raise RuntimeError("没有成功解析任何帧！")

    target_w, target_h = get_video_size(all_frames)
    log(f"\n视频分辨率: {target_w}x{target_h}，共 {len(all_frames)} 帧")
    log("写入临时帧图像...")

    # ── 第二遍：导出帧到临时目录 + 生成 ffmpeg concat 列表 ──
    tmpdir = tempfile.mkdtemp(prefix="webp2vid_")
    concat_file = os.path.join(tmpdir, "concat.txt")

    try:
        with open(concat_file, "w", encoding="utf-8") as cf:
            for j, (img, dur_ms) in enumerate(all_frames):
                rgb = composite_on_bg(img)
                rgb = pad_frame(rgb, target_w, target_h)
                frame_path = os.path.join(tmpdir, f"frame_{j:06d}.png")
                rgb.save(frame_path, "PNG")
                duration_sec = dur_ms / 1000.0
                cf.write(f"file '{frame_path}'\n")
                cf.write(f"duration {duration_sec:.6f}\n")
                if progress_cb:
                    progress_cb(total_files + j + 1, total_files * 2 + len(all_frames))

        log("调用 ffmpeg 编码视频...")

        ext = Path(output_path).suffix.lower()
        if ext == ".avi":
            extra = ["-c:v", codec]
        elif ext == ".mov":
            extra = ["-c:v", codec, "-movflags", "+faststart"]
        else:  # mp4
            extra = ["-c:v", codec, "-crf", str(crf), "-preset", "medium",
                     "-movflags", "+faststart", "-pix_fmt", "yuv420p"]

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            *extra,
            output_path,
        ]
        log("命令: " + " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 错误:\n{result.stderr[-2000:]}")

        log(f"\n✅ 完成！输出: {output_path}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ──────────────────────────────────────────────
# 图形界面
# ──────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WebP动画 → 视频")
        self.resizable(True, True)
        self.minsize(600, 500)
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = 700, 560
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        pad = dict(padx=10, pady=5)

        # ── 文件夹选择 ──
        frm_src = ttk.LabelFrame(self, text="输入文件夹")
        frm_src.pack(fill="x", **pad)

        self.var_src = tk.StringVar()
        ttk.Entry(frm_src, textvariable=self.var_src, width=55).pack(
            side="left", fill="x", expand=True, padx=(6, 4), pady=6)
        ttk.Button(frm_src, text="浏览…", command=self._pick_src).pack(
            side="left", padx=(0, 6), pady=6)

        # ── 文件列表预览 ──
        frm_list = ttk.LabelFrame(self, text="将处理的文件（按文件名排序）")
        frm_list.pack(fill="both", expand=True, **pad)

        self.listbox = tk.Listbox(frm_list, selectmode="extended",
                                  font=("Courier", 10))
        sb = ttk.Scrollbar(frm_list, orient="vertical",
                           command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True, padx=4, pady=4)

        # ── 输出设置 ──
        frm_out = ttk.LabelFrame(self, text="输出设置")
        frm_out.pack(fill="x", **pad)

        ttk.Label(frm_out, text="输出文件:").grid(
            row=0, column=0, sticky="w", padx=6, pady=4)
        self.var_out = tk.StringVar()
        ttk.Entry(frm_out, textvariable=self.var_out, width=42).grid(
            row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frm_out, text="另存为…", command=self._pick_out).grid(
            row=0, column=2, padx=(0, 6), pady=4)

        ttk.Label(frm_out, text="格式/编码:").grid(
            row=1, column=0, sticky="w", padx=6, pady=4)
        self.var_codec = tk.StringVar(value="libx264 (MP4, 最兼容)")
        codec_map = {
            "libx264 (MP4, 最兼容)": "libx264",
            "libx265 (MP4, 更小体积)": "libx265",
            "libvpx-vp9 (WebM)": "libvpx-vp9",
            "mjpeg (AVI, 无损画质)": "mjpeg",
        }
        self._codec_map = codec_map
        cb = ttk.Combobox(frm_out, textvariable=self.var_codec,
                          values=list(codec_map.keys()), state="readonly", width=28)
        cb.grid(row=1, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(frm_out, text="质量(CRF):").grid(
            row=2, column=0, sticky="w", padx=6, pady=4)
        self.var_crf = tk.IntVar(value=18)
        sc = ttk.Scale(frm_out, from_=0, to=51, variable=self.var_crf,
                       orient="horizontal", length=180,
                       command=lambda v: self.lbl_crf.config(
                           text=f"{int(float(v))}  (0=最佳, 51=最差)"))
        sc.grid(row=2, column=1, sticky="w", padx=4, pady=4)
        self.lbl_crf = ttk.Label(frm_out, text="18  (0=最佳, 51=最差)")
        self.lbl_crf.grid(row=2, column=2, sticky="w", padx=4)

        frm_out.columnconfigure(1, weight=1)

        # ── 进度 ──
        self.var_progress = tk.DoubleVar()
        self.progress = ttk.Progressbar(self, variable=self.var_progress,
                                        maximum=100)
        self.progress.pack(fill="x", padx=10, pady=(4, 0))

        self.lbl_status = ttk.Label(self, text="就绪", anchor="w")
        self.lbl_status.pack(fill="x", padx=12, pady=(2, 0))

        # ── 日志 ──
        frm_log = ttk.LabelFrame(self, text="日志")
        frm_log.pack(fill="both", expand=False, padx=10, pady=(4, 4))
        self.log_text = tk.Text(frm_log, height=6, font=("Courier", 9),
                                state="disabled", wrap="word")
        log_sb = ttk.Scrollbar(frm_log, orient="vertical",
                               command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # ── 按钮 ──
        frm_btn = ttk.Frame(self)
        frm_btn.pack(pady=6)
        ttk.Button(frm_btn, text="🔄  刷新列表", command=self._refresh_list).pack(
            side="left", padx=6)
        self.btn_start = ttk.Button(frm_btn, text="▶  开始转换",
                                    command=self._start)
        self.btn_start.pack(side="left", padx=6)

    # ── 事件处理 ──

    def _pick_src(self):
        d = filedialog.askdirectory(title="选择包含WebP文件的文件夹")
        if d:
            self.var_src.set(d)
            # 自动设置输出路径
            if not self.var_out.get():
                self.var_out.set(str(Path(d) / "output.mp4"))
            self._refresh_list()

    def _pick_out(self):
        f = filedialog.asksaveasfilename(
            title="保存视频为",
            defaultextension=".mp4",
            filetypes=[
                ("MP4 视频", "*.mp4"),
                ("MOV 视频", "*.mov"),
                ("AVI 视频", "*.avi"),
                ("所有文件", "*.*"),
            ],
        )
        if f:
            self.var_out.set(f)

    def _refresh_list(self):
        src = self.var_src.get().strip()
        self.listbox.delete(0, "end")
        if not src or not os.path.isdir(src):
            return
        files = sorted(
            [f for f in Path(src).iterdir()
             if f.suffix.lower() == ".webp"],
            key=lambda p: p.name
        )
        for f in files:
            self.listbox.insert("end", f.name)
        self.lbl_status.config(
            text=f"找到 {len(files)} 个 .webp 文件")

    def _get_files(self) -> list[str]:
        src = self.var_src.get().strip()
        return sorted(
            [str(f) for f in Path(src).iterdir()
             if f.suffix.lower() == ".webp"],
            key=lambda p: Path(p).name,
        )

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_progress(self, current, total):
        pct = current / total * 100 if total else 0
        self.var_progress.set(pct)
        self.lbl_status.config(text=f"处理中… {current}/{total}")
        self.update_idletasks()

    def _start(self):
        src = self.var_src.get().strip()
        out = self.var_out.get().strip()

        if not src or not os.path.isdir(src):
            messagebox.showerror("错误", "请先选择有效的输入文件夹")
            return
        if not out:
            messagebox.showerror("错误", "请指定输出文件路径")
            return

        files = self._get_files()
        if not files:
            messagebox.showerror("错误", "文件夹内没有找到 .webp 文件")
            return

        codec_label = self.var_codec.get()
        codec = self._codec_map[codec_label]
        crf = self.var_crf.get()

        # 检查 ffmpeg
        if not shutil.which("ffmpeg"):
            messagebox.showerror(
                "缺少 ffmpeg",
                "未找到 ffmpeg！\n\n"
                "请先安装：\n"
                "  macOS: brew install ffmpeg\n"
                "  Ubuntu: sudo apt install ffmpeg\n"
                "  Windows: https://ffmpeg.org/download.html",
            )
            return

        self.btn_start.configure(state="disabled")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        def run():
            try:
                convert_webps_to_video(
                    files,
                    out,
                    codec=codec,
                    crf=crf,
                    progress_cb=lambda c, t: self.after(0, self._set_progress, c, t),
                    log_cb=lambda m: self.after(0, self._log, m),
                )
                self.after(0, lambda: messagebox.showinfo(
                    "完成", f"视频已生成：\n{out}"))
                self.after(0, lambda: self.var_progress.set(100))
                self.after(0, lambda: self.lbl_status.config(text="✅ 转换完成"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("错误", str(e)))
                self.after(0, lambda: self.lbl_status.config(text="❌ 出错"))
            finally:
                self.after(0, lambda: self.btn_start.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()


# ──────────────────────────────────────────────
# 命令行入口
# ──────────────────────────────────────────────

def cli_mode(folder: str):
    files = sorted(
        [str(f) for f in Path(folder).iterdir()
         if f.suffix.lower() == ".webp"],
        key=lambda p: Path(p).name,
    )
    if not files:
        print("文件夹内没有找到 .webp 文件")
        sys.exit(1)
    out = str(Path(folder) / "output.mp4")
    print(f"找到 {len(files)} 个文件，输出到: {out}")
    convert_webps_to_video(files, out)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_mode(sys.argv[1])
    else:
        app = App()
        app.mainloop()
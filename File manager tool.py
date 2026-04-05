"""
文件批量管理工具
功能1: 删除指定目录下所有文件夹名称的前X个字符
功能2: 检索图片文件，将【】及其内容移至文件名开头
"""

import os
import sys
import re
import json
import logging
import shutil
import ctypes
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading

# ─────────────────────────────────────────────
# DPI 感知（Windows 高分辨率支持）
# ─────────────────────────────────────────────
def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

set_dpi_aware()

# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────
APP_NAME  = "文件批量管理工具"
LOG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_manager.log")
CFG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_manager_cfg.json")

IMG_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
    ".tiff", ".tif", ".ico", ".heic", ".heif", ".avif",
    ".svg", ".raw", ".cr2", ".nef", ".arw", ".dng",
    ".jfif", ".pjpeg", ".pjp"
}

# 颜色方案
CLR = {
    "bg"        : "#1C1C2E",
    "bg2"       : "#252540",
    "bg3"       : "#2E2E50",
    "card"      : "#1E1E38",
    "accent"    : "#6C63FF",
    "accent2"   : "#FF6584",
    "accent3"   : "#43E97B",
    "text"      : "#E8E8F0",
    "text_dim"  : "#888899",
    "border"    : "#3A3A60",
    "check_on"  : "#43E97B",   # 勾选颜色——与深色背景高对比
    "check_off" : "#444466",
    "warning"   : "#FFB347",
    "error"     : "#FF5555",
    "row_alt"   : "#222240",
    "row_sel"   : "#3A3A70",
}

# ─────────────────────────────────────────────
# 日志
# ─────────────────────────────────────────────
def init_logger():
    logger = logging.getLogger("FMT")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)
    return logger

logger = init_logger()

def log(msg: str, level="info"):
    getattr(logger, level)(msg)

# ─────────────────────────────────────────────
# 配置持久化
# ─────────────────────────────────────────────
def load_cfg() -> dict:
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cfg(data: dict):
    try:
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"保存配置失败: {e}", "warning")

# ─────────────────────────────────────────────
# 业务逻辑
# ─────────────────────────────────────────────

def get_folders(directory: str) -> list[str]:
    """返回目录下的直接子文件夹名列表"""
    try:
        return [
            d for d in os.listdir(directory)
            if os.path.isdir(os.path.join(directory, d))
        ]
    except Exception as e:
        log(f"读取目录失败 {directory}: {e}", "error")
        return []

def strip_prefix_preview(folders: list[str], x: int) -> list[dict]:
    """生成前缀删除预览列表"""
    result = []
    for name in folders:
        new_name = name[x:] if len(name) > x else ""
        result.append({
            "original": name,
            "new_name": new_name,
            "valid"   : bool(new_name),
        })
    return result

def do_strip_prefix(directory: str, items: list[dict]) -> tuple[int, int]:
    """执行前缀删除，返回 (成功数, 失败数)"""
    ok = fail = 0
    for item in items:
        if not item.get("selected", True):
            continue
        if not item["valid"]:
            log(f"跳过（结果为空）: {item['original']}", "warning")
            fail += 1
            continue
        src = os.path.join(directory, item["original"])
        dst = os.path.join(directory, item["new_name"])
        try:
            if os.path.exists(dst):
                raise FileExistsError(f"目标已存在: {dst}")
            os.rename(src, dst)
            log(f"[前缀删除] {item['original']} → {item['new_name']}")
            ok += 1
        except Exception as e:
            log(f"[前缀删除] 失败 {item['original']}: {e}", "error")
            fail += 1
    return ok, fail


def get_images(directory: str) -> list[str]:
    """返回目录下所有图片文件名（已排序）"""
    try:
        return sorted([
            f for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
            and Path(f).suffix.lower() in IMG_EXTS
        ])
    except Exception as e:
        log(f"读取图片失败 {directory}: {e}", "error")
        return []

def get_all_files(directory: str) -> list[str]:
    """返回目录下所有文件名（已排序）"""
    try:
        return sorted([
            f for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
        ])
    except Exception as e:
        log(f"读取文件失败 {directory}: {e}", "error")
        return []

_BRACKET_RE = re.compile(r"(【[^】]*】)")

# ── 四种操作模式的预览生成 ──────────────────────────

def preview_bracket_to_head(names: list[str]) -> list[dict]:
    """【...】移至文件名开头"""
    result = []
    for name in names:
        stem, suffix = Path(name).stem, Path(name).suffix
        brackets = _BRACKET_RE.findall(stem)
        if brackets:
            clean    = _BRACKET_RE.sub("", stem)
            new_name = "".join(brackets) + clean + suffix
            changed  = new_name != name
        else:
            new_name, changed = name, False
        result.append({"original": name, "new_name": new_name,
                        "has_bracket": bool(brackets), "changed": changed,
                        "valid": True})
    return result

def preview_bracket_to_tail(names: list[str]) -> list[dict]:
    """【...】移至文件名末尾"""
    result = []
    for name in names:
        stem, suffix = Path(name).stem, Path(name).suffix
        brackets = _BRACKET_RE.findall(stem)
        if brackets:
            clean    = _BRACKET_RE.sub("", stem)
            new_name = clean + "".join(brackets) + suffix
            changed  = new_name != name
        else:
            new_name, changed = name, False
        result.append({"original": name, "new_name": new_name,
                        "has_bracket": bool(brackets), "changed": changed,
                        "valid": True})
    return result

def preview_bracket_delete(names: list[str]) -> list[dict]:
    """删除【...】及其内容"""
    result = []
    for name in names:
        stem, suffix = Path(name).stem, Path(name).suffix
        brackets = _BRACKET_RE.findall(stem)
        if brackets:
            new_stem = _BRACKET_RE.sub("", stem).strip()
            valid    = bool(new_stem)
            new_name = (new_stem + suffix) if valid else ""
            changed  = (name != new_name) if valid else True
        else:
            new_name, changed, valid = name, False, True
        result.append({"original": name, "new_name": new_name,
                        "has_bracket": bool(brackets), "changed": changed,
                        "valid": valid})
    return result

def preview_add_string(names: list[str], text: str, position: str) -> list[dict]:
    """在文件名开头或末尾添加字符串。position: 'head' | 'tail'"""
    result = []
    for name in names:
        stem, suffix = Path(name).stem, Path(name).suffix
        if not text:
            new_name, changed = name, False
        elif position == "head":
            new_name = text + stem + suffix
            changed  = True
        else:
            new_name = stem + text + suffix
            changed  = True
        result.append({"original": name, "new_name": new_name,
                        "changed": changed, "valid": True})
    return result

def do_rename(directory: str, items: list[dict], tag: str) -> tuple[int, int]:
    """通用执行重命名，返回 (成功数, 失败数)"""
    ok = fail = 0
    for item in items:
        if not item.get("selected", True) or not item.get("changed", False):
            continue
        if not item.get("valid", True):
            log(f"[{tag}] 跳过（结果为空）: {item['original']}", "warning")
            fail += 1
            continue
        src = os.path.join(directory, item["original"])
        dst = os.path.join(directory, item["new_name"])
        try:
            if os.path.exists(dst):
                raise FileExistsError(f"目标已存在: {dst}")
            os.rename(src, dst)
            log(f"[{tag}] {item['original']} → {item['new_name']}")
            ok += 1
        except Exception as e:
            log(f"[{tag}] 失败 {item['original']}: {e}", "error")
            fail += 1
    return ok, fail


# ─────────────────────────────────────────────
# 自定义 CheckButton（高对比度）
# ─────────────────────────────────────────────
class FancyCheck(tk.Canvas):
    SIZE = 20

    def __init__(self, master, variable: tk.BooleanVar, **kw):
        kw.setdefault("bg", CLR["bg2"])
        super().__init__(master,
            width=self.SIZE, height=self.SIZE,
            bd=0, highlightthickness=0,
            cursor="hand2", **kw)
        self.var = variable
        self._draw()
        self.var.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", self._toggle)

    def _toggle(self, _=None):
        self.var.set(not self.var.get())

    def _draw(self):
        self.delete("all")
        s = self.SIZE
        checked = self.var.get()
        border = CLR["check_on"] if checked else CLR["border"]
        fill   = CLR["check_on"] if checked else CLR["bg3"]
        self.create_rectangle(2, 2, s-2, s-2,
            outline=border, fill=fill, width=2)
        if checked:
            # 画对勾
            self.create_line(5, s//2, s//2-1, s-5,
                fill="#0A0A1A", width=2.5, capstyle="round")
            self.create_line(s//2-1, s-5, s-4, 4,
                fill="#0A0A1A", width=2.5, capstyle="round")


# ─────────────────────────────────────────────
# 预览表格（通用）
# ─────────────────────────────────────────────
class PreviewTable(tk.Frame):
    """
    列: [☑] 原名称  →  新名称  [状态]
    """
    COL_W = [28, 340, 30, 340, 100]
    HEADERS = ["", "原名称", "", "新名称", "状态"]
    ROW_H = 28

    def __init__(self, master, **kw):
        super().__init__(master, bg=CLR["bg2"], **kw)
        self.items: list[dict] = []
        self.vars : list[tk.BooleanVar] = []
        self._build()

    def _build(self):
        # 表头
        hdr = tk.Frame(self, bg=CLR["bg3"])
        hdr.pack(fill="x")
        widths = self.COL_W
        labels = self.HEADERS
        for i, (w, h) in enumerate(zip(widths, labels)):
            tk.Label(hdr, text=h, bg=CLR["bg3"], fg=CLR["accent"],
                     font=("微软雅黑", 10, "bold"),
                     width=w//7, anchor="w" if i>0 else "center"
                    ).pack(side="left", padx=(4 if i==0 else 2), pady=4)

        # 滚动区
        self.canvas = tk.Canvas(self, bg=CLR["bg2"],
                                highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical",
                           command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=CLR["bg2"])
        self._win_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_cfg)
        self.canvas.bind("<Configure>", self._on_canvas_cfg)
        self.canvas.bind("<MouseWheel>", self._on_scroll)

    def _on_inner_cfg(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_cfg(self, e):
        self.canvas.itemconfig(self._win_id, width=e.width)

    def _on_scroll(self, e):
        self.canvas.yview_scroll(int(-1*(e.delta/120)), "units")

    def load(self, items: list[dict]):
        self.items = items
        self.vars  = []
        for w in self.inner.winfo_children():
            w.destroy()

        for i, item in enumerate(items):
            bg = CLR["row_alt"] if i % 2 else CLR["bg2"]
            row = tk.Frame(self.inner, bg=bg)
            row.pack(fill="x")

            var = tk.BooleanVar(value=item.get("selected", True))
            self.vars.append(var)

            cb = FancyCheck(row, var, bg=bg)
            cb.pack(side="left", padx=6, pady=4)

            orig = item.get("original", "")
            new  = item.get("new_name", "")
            st   = self._status(item)
            st_c = self._status_color(item)

            tk.Label(row, text=orig, bg=bg, fg=CLR["text"],
                     font=("微软雅黑", 9), anchor="w",
                     width=38).pack(side="left", padx=2)
            tk.Label(row, text="→", bg=bg, fg=CLR["text_dim"],
                     font=("微软雅黑", 10)).pack(side="left")
            tk.Label(row, text=new, bg=bg, fg=CLR["accent3"],
                     font=("微软雅黑", 9), anchor="w",
                     width=38).pack(side="left", padx=2)
            tk.Label(row, text=st, bg=bg, fg=st_c,
                     font=("微软雅黑", 9, "bold"),
                     width=12).pack(side="left", padx=4)

    def _status(self, item):
        if not item.get("valid", True):
            return "⚠ 结果为空"
        if not item.get("changed", True):
            return "— 无需修改"
        if not item.get("has_bracket", True):
            return "— 无括号"
        return "✓ 将重命名"

    def _status_color(self, item):
        if not item.get("valid", True):
            return CLR["error"]
        if not item.get("changed", True):
            return CLR["text_dim"]
        return CLR["check_on"]

    def get_selections(self) -> list[bool]:
        return [v.get() for v in self.vars]

    def select_all(self, state=True):
        for v in self.vars:
            v.set(state)

    def apply_selections(self):
        for item, var in zip(self.items, self.vars):
            item["selected"] = var.get()


# ─────────────────────────────────────────────
# 主窗口
# ─────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_cfg()
        self.title(APP_NAME)
        self.configure(bg=CLR["bg"])
        self._set_geometry()
        self._build_style()
        self._build_ui()
        self._restore_cfg()
        log("=" * 60)
        log(f"程序启动  版本 1.0  日志: {LOG_FILE}")

    def _set_geometry(self):
        # 针对 2560×1600 150% 缩放 → 逻辑分辨率约 1707×1067
        self.geometry("1280x820")
        self.minsize(960, 640)
        # 居中
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 1280, 820
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        # Notebook
        s.configure("TNotebook",
            background=CLR["bg"], borderwidth=0)
        s.configure("TNotebook.Tab",
            background=CLR["bg3"], foreground=CLR["text_dim"],
            font=("微软雅黑", 11, "bold"),
            padding=[18, 8])
        s.map("TNotebook.Tab",
            background=[("selected", CLR["accent"]),
                        ("active",   CLR["bg2"])],
            foreground=[("selected", "#FFFFFF"),
                        ("active",   CLR["text"])])
        # Scrollbar
        s.configure("Vertical.TScrollbar",
            background=CLR["bg3"], troughcolor=CLR["bg"],
            arrowcolor=CLR["accent"], borderwidth=0)
        s.map("Vertical.TScrollbar",
            background=[("active", CLR["accent"])])

    # ── UI 构建 ──────────────────────────────
    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self, bg=CLR["bg"], height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="⚙  " + APP_NAME,
                 bg=CLR["bg"], fg=CLR["accent"],
                 font=("微软雅黑", 16, "bold")).pack(side="left", padx=20, pady=10)

        # 日志按钮
        tk.Button(header, text="📋 查看日志",
                  bg=CLR["bg3"], fg=CLR["text"],
                  font=("微软雅黑", 10),
                  relief="flat", cursor="hand2",
                  command=self._open_log,
                  padx=14, pady=6).pack(side="right", padx=16, pady=10)

        # 选项卡
        nb = ttk.Notebook(self, style="TNotebook")
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tab1 = tk.Frame(nb, bg=CLR["bg"])
        tab2 = tk.Frame(nb, bg=CLR["bg"])
        nb.add(tab1, text="  📁 前缀删除  ")
        nb.add(tab2, text="  🖼 括号重命名  ")

        self._build_tab1(tab1)
        self._build_tab2(tab2)

    # ────────── TAB 1 ──────────
    def _build_tab1(self, parent):
        # 参数卡
        card = tk.Frame(parent, bg=CLR["card"],
                        relief="flat", bd=0)
        card.pack(fill="x", padx=16, pady=12)

        # 标题
        tk.Label(card, text="功能一：批量删除文件夹名称前 X 个字符",
                 bg=CLR["card"], fg=CLR["text"],
                 font=("微软雅黑", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 6))

        sep = tk.Frame(card, bg=CLR["border"], height=1)
        sep.pack(fill="x", padx=16, pady=4)

        # 目录选择
        row1 = tk.Frame(card, bg=CLR["card"])
        row1.pack(fill="x", padx=16, pady=8)
        tk.Label(row1, text="目标目录：", bg=CLR["card"],
                 fg=CLR["text"], font=("微软雅黑", 10),
                 width=10, anchor="w").pack(side="left")
        self.t1_dir = tk.StringVar()
        tk.Entry(row1, textvariable=self.t1_dir,
                 bg=CLR["bg3"], fg=CLR["text"],
                 insertbackground=CLR["text"],
                 font=("微软雅黑", 10), relief="flat",
                 bd=0).pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)
        self._btn(row1, "📂 浏览",
                  lambda: self._browse(self.t1_dir)).pack(side="left")

        # X 值
        row2 = tk.Frame(card, bg=CLR["card"])
        row2.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(row2, text="删除字符数 X：", bg=CLR["card"],
                 fg=CLR["text"], font=("微软雅黑", 10),
                 width=12, anchor="w").pack(side="left")
        self.t1_x = tk.IntVar(value=self.cfg.get("t1_x", 2))
        spin = tk.Spinbox(row2, from_=1, to=999,
                          textvariable=self.t1_x,
                          bg=CLR["bg3"], fg=CLR["text"],
                          insertbackground=CLR["text"],
                          buttonbackground=CLR["bg3"],
                          font=("微软雅黑", 11), relief="flat",
                          width=6)
        spin.pack(side="left")
        tk.Label(row2, text="（将删除每个子文件夹名称开头的前 X 个字符）",
                 bg=CLR["card"], fg=CLR["text_dim"],
                 font=("微软雅黑", 9)).pack(side="left", padx=12)

        # 按钮区
        btn_row = tk.Frame(card, bg=CLR["card"])
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        self._btn(btn_row, "🔍 预览",
                  self._t1_preview, accent=True).pack(side="left", padx=(0, 10))
        self._btn(btn_row, "☑ 全选",
                  lambda: self.t1_table.select_all(True)).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "☐ 全不选",
                  lambda: self.t1_table.select_all(False)).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "✅ 执行重命名",
                  self._t1_execute, color=CLR["accent3"]).pack(side="right")

        # 预览表格
        self.t1_table = PreviewTable(parent)
        self.t1_table.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # 状态栏
        self.t1_status = tk.StringVar(value="请先选择目录并点击「预览」")
        tk.Label(parent, textvariable=self.t1_status,
                 bg=CLR["bg"], fg=CLR["text_dim"],
                 font=("微软雅黑", 9), anchor="w").pack(
                     fill="x", padx=20, pady=(0, 6))

    # ────────── TAB 2 ──────────
    def _build_tab2(self, parent):
        # ── 参数卡 ──
        card = tk.Frame(parent, bg=CLR["card"], relief="flat", bd=0)
        card.pack(fill="x", padx=16, pady=12)

        tk.Label(card, text="功能二：图片文件批量重命名",
                 bg=CLR["card"], fg=CLR["text"],
                 font=("微软雅黑", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Frame(card, bg=CLR["border"], height=1).pack(fill="x", padx=16, pady=(0, 8))

        # 目录行
        row_dir = tk.Frame(card, bg=CLR["card"])
        row_dir.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(row_dir, text="目标目录：", bg=CLR["card"],
                 fg=CLR["text"], font=("微软雅黑", 10),
                 width=10, anchor="w").pack(side="left")
        self.t2_dir = tk.StringVar()
        tk.Entry(row_dir, textvariable=self.t2_dir,
                 bg=CLR["bg3"], fg=CLR["text"],
                 insertbackground=CLR["text"],
                 font=("微软雅黑", 10), relief="flat", bd=0
                 ).pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)
        self._btn(row_dir, "📂 浏览",
                  lambda: self._browse(self.t2_dir)).pack(side="left")

        # ── 操作模式选择（单选，互斥）──
        tk.Label(card, text="操作模式：", bg=CLR["card"],
                 fg=CLR["text_dim"], font=("微软雅黑", 9)
                 ).pack(anchor="w", padx=16)

        mode_frame = tk.Frame(card, bg=CLR["card"])
        mode_frame.pack(fill="x", padx=16, pady=(2, 8))

        self.t2_mode = tk.StringVar(value=self.cfg.get("t2_mode", "to_head"))

        MODES = [
            ("to_head",  "【】移至开头",  "将【...】内容整体挪到文件名最前面"),
            ("to_tail",  "【】移至末尾",  "将【...】内容整体挪到文件名最后面"),
            ("delete",   "删除【】内容",  "直接删去所有【...】及其中的字符"),
            ("add_str",  "添加字符串",    "在所有文件名的开头或末尾追加指定文本"),
        ]

        self._mode_btns = {}
        for val, label, tip in MODES:
            btn = tk.Radiobutton(
                mode_frame, text=label, variable=self.t2_mode, value=val,
                bg=CLR["card"], fg=CLR["text"],
                selectcolor=CLR["accent"],
                activebackground=CLR["card"], activeforeground=CLR["text"],
                font=("微软雅黑", 10), cursor="hand2",
                command=self._t2_on_mode_change,
                indicatoron=0,                   # 整个按钮作为选中块
                relief="flat", bd=1,
                padx=14, pady=6,
                width=12,
            )
            btn.pack(side="left", padx=(0, 6))
            self._mode_btns[val] = btn

        # 提示文字
        self.t2_mode_tip = tk.StringVar(value=MODES[0][2])
        tk.Label(card, textvariable=self.t2_mode_tip,
                 bg=CLR["card"], fg=CLR["text_dim"],
                 font=("微软雅黑", 9)).pack(anchor="w", padx=16, pady=(0, 4))

        # ── 添加字符串子选项（仅 add_str 模式可见）──
        self.t2_addstr_frame = tk.Frame(card, bg=CLR["card"])
        self.t2_addstr_frame.pack(fill="x", padx=16, pady=(0, 6))

        tk.Label(self.t2_addstr_frame, text="添加文本：",
                 bg=CLR["card"], fg=CLR["text"],
                 font=("微软雅黑", 10)).pack(side="left")
        self.t2_add_text = tk.StringVar(value=self.cfg.get("t2_add_text", ""))
        tk.Entry(self.t2_addstr_frame, textvariable=self.t2_add_text,
                 bg=CLR["bg3"], fg=CLR["text"],
                 insertbackground=CLR["text"],
                 font=("微软雅黑", 10), relief="flat", bd=0,
                 width=20).pack(side="left", padx=(0, 16), ipady=5)

        tk.Label(self.t2_addstr_frame, text="位置：",
                 bg=CLR["card"], fg=CLR["text"],
                 font=("微软雅黑", 10)).pack(side="left")
        self.t2_add_pos = tk.StringVar(value=self.cfg.get("t2_add_pos", "head"))
        for val, label in [("head", "文件名开头"), ("tail", "文件名末尾")]:
            tk.Radiobutton(
                self.t2_addstr_frame, text=label,
                variable=self.t2_add_pos, value=val,
                bg=CLR["card"], fg=CLR["text"],
                selectcolor=CLR["bg3"],
                activebackground=CLR["card"],
                font=("微软雅黑", 10), cursor="hand2",
            ).pack(side="left", padx=(0, 12))

        # ── 过滤开关 & 文件范围 ──
        filter_frame = tk.Frame(card, bg=CLR["card"])
        filter_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.t2_only_changed = tk.BooleanVar(
            value=self.cfg.get("t2_only_changed", True))
        FancyCheck(filter_frame, self.t2_only_changed,
                   bg=CLR["card"]).pack(side="left")
        tk.Label(filter_frame, text="  仅显示需要修改的文件",
                 bg=CLR["card"], fg=CLR["text"],
                 font=("微软雅黑", 10)).pack(side="left", padx=(0, 24))

        self.t2_img_only = tk.BooleanVar(
            value=self.cfg.get("t2_img_only", True))
        FancyCheck(filter_frame, self.t2_img_only,
                   bg=CLR["card"]).pack(side="left")
        tk.Label(filter_frame, text="  仅处理图片格式",
                 bg=CLR["card"], fg=CLR["text"],
                 font=("微软雅黑", 10)).pack(side="left")

        # ── 按钮行 ──
        btn_row = tk.Frame(card, bg=CLR["card"])
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        self._btn(btn_row, "🔍 预览",
                  self._t2_preview, accent=True).pack(side="left", padx=(0, 10))
        self._btn(btn_row, "☑ 全选",
                  lambda: self.t2_table.select_all(True)).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "☐ 全不选",
                  lambda: self.t2_table.select_all(False)).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "✅ 执行重命名",
                  self._t2_execute, color=CLR["accent3"]).pack(side="right")

        # 预览表格
        self.t2_table = PreviewTable(parent)
        self.t2_table.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # 状态栏
        self.t2_status = tk.StringVar(value="请先选择目录并点击「预览」")
        tk.Label(parent, textvariable=self.t2_status,
                 bg=CLR["bg"], fg=CLR["text_dim"],
                 font=("微软雅黑", 9), anchor="w").pack(
                     fill="x", padx=20, pady=(0, 6))

        # 初始化模式 UI 状态
        self._t2_on_mode_change()

    # ── 通用组件 ───────────────────────────────
    def _btn(self, parent, text, cmd, accent=False, color=None):
        bg = color if color else (CLR["accent"] if accent else CLR["bg3"])
        fg = "#FFFFFF" if (accent or color) else CLR["text"]
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=fg, activebackground=CLR["border"],
                         activeforeground=CLR["text"],
                         font=("微软雅黑", 10, "bold" if accent else "normal"),
                         relief="flat", cursor="hand2",
                         padx=16, pady=7, bd=0)

    def _browse(self, var: tk.StringVar):
        d = filedialog.askdirectory(initialdir=var.get() or "/")
        if d:
            var.set(d)

    # ── Tab1 逻辑 ──────────────────────────────
    def _t1_preview(self):
        d = self.t1_dir.get().strip()
        x = self.t1_x.get()
        if not d or not os.path.isdir(d):
            messagebox.showwarning("提示", "请选择有效目录")
            return
        folders = get_folders(d)
        if not folders:
            self.t1_status.set("⚠ 该目录下没有子文件夹")
            return
        items = strip_prefix_preview(folders, x)
        for item in items:
            item["selected"] = True
        self.t1_table.load(items)
        self.t1_status.set(
            f"共找到 {len(folders)} 个子文件夹，将删除前 {x} 个字符")
        # 保存参数到日志
        log(f"[功能1-预览] 目录={d}  X={x}  文件夹数={len(folders)}")
        self._save_params()

    def _t1_execute(self):
        self.t1_table.apply_selections()
        items = self.t1_table.items
        if not items:
            messagebox.showinfo("提示", "请先点击「预览」")
            return
        d = self.t1_dir.get().strip()
        sel = [i for i in items if i.get("selected") and i.get("valid")]
        if not sel:
            messagebox.showinfo("提示", "没有选中任何可执行的项")
            return
        if not messagebox.askyesno("确认",
            f"即将重命名 {len(sel)} 个文件夹，是否继续？"):
            return
        ok, fail = do_strip_prefix(d, items)
        messagebox.showinfo("完成",
            f"执行完成\n成功: {ok} 个\n失败: {fail} 个")
        self.t1_status.set(f"✅ 执行完成 — 成功 {ok} 个，失败 {fail} 个")
        log(f"[功能1-执行] 目录={d}  成功={ok}  失败={fail}")
        self._t1_preview()   # 刷新预览

    # ── Tab2 逻辑 ──────────────────────────────

    # 模式提示文本映射
    _MODE_TIPS = {
        "to_head": "将【...】内容整体挪到文件名最前面",
        "to_tail": "将【...】内容整体挪到文件名最后面",
        "delete" : "直接删去所有【...】及其中的字符",
        "add_str": "在所有文件名的开头或末尾追加指定文本",
    }

    def _t2_on_mode_change(self, *_):
        mode = self.t2_mode.get()
        # 更新提示
        self.t2_mode_tip.set(self._MODE_TIPS.get(mode, ""))
        # 显示/隐藏添加字符串子面板
        if mode == "add_str":
            self.t2_addstr_frame.pack(fill="x", padx=16, pady=(0, 6),
                                       before=self.t2_addstr_frame.master.winfo_children()[
                                           list(self.t2_addstr_frame.master.winfo_children()).index(
                                               self.t2_addstr_frame)])
        # 用更简单的方式控制可见性
        widgets = self.t2_addstr_frame.winfo_children()
        state = "normal" if mode == "add_str" else "disabled"
        for w in widgets:
            try:
                w.configure(state=state)
            except Exception:
                pass
        # 更新模式按钮样式
        for val, btn in self._mode_btns.items():
            if val == mode:
                btn.configure(bg=CLR["accent"], fg="#FFFFFF",
                               relief="solid")
            else:
                btn.configure(bg=CLR["bg3"], fg=CLR["text"],
                               relief="flat")

    def _t2_get_names(self) -> list[str]:
        """根据 img_only 开关返回文件列表"""
        d = self.t2_dir.get().strip()
        if self.t2_img_only.get():
            return get_images(d)
        return get_all_files(d)

    def _t2_build_items(self) -> list[dict]:
        """根据当前模式生成预览数据"""
        mode  = self.t2_mode.get()
        names = self._t2_get_names()
        if mode == "to_head":
            return preview_bracket_to_head(names)
        elif mode == "to_tail":
            return preview_bracket_to_tail(names)
        elif mode == "delete":
            return preview_bracket_delete(names)
        else:  # add_str
            text = self.t2_add_text.get()
            pos  = self.t2_add_pos.get()
            return preview_add_string(names, text, pos)

    def _t2_preview(self):
        d = self.t2_dir.get().strip()
        if not d or not os.path.isdir(d):
            messagebox.showwarning("提示", "请选择有效目录")
            return
        mode = self.t2_mode.get()
        if mode == "add_str" and not self.t2_add_text.get().strip():
            messagebox.showwarning("提示", "「添加字符串」模式下请先填写要添加的文本")
            return

        items = self._t2_build_items()
        if not items:
            kind = "图片" if self.t2_img_only.get() else "文件"
            self.t2_status.set(f"⚠ 该目录下没有找到{kind}")
            return

        total = len(items)
        for item in items:
            item["selected"] = item.get("changed", False)

        if self.t2_only_changed.get():
            items = [i for i in items if i.get("changed")]

        self.t2_table.load(items)
        changed_n = sum(1 for i in items if i.get("changed"))
        self.t2_status.set(
            f"共扫描 {total} 个文件，其中 {changed_n} 个将被修改")
        log(f"[功能2-预览] 目录={d}  模式={mode}  总数={total}  需改={changed_n}")
        self._save_params()

    def _t2_execute(self):
        self.t2_table.apply_selections()
        items = self.t2_table.items
        if not items:
            messagebox.showinfo("提示", "请先点击「预览」")
            return
        d    = self.t2_dir.get().strip()
        mode = self.t2_mode.get()
        sel  = [i for i in items if i.get("selected") and i.get("changed")]
        if not sel:
            messagebox.showinfo("提示", "没有选中任何需要修改的文件")
            return
        if not messagebox.askyesno("确认",
                f"即将重命名 {len(sel)} 个文件，是否继续？"):
            return
        tag_map = {"to_head": "【】移开头", "to_tail": "【】移末尾",
                   "delete": "删除【】", "add_str": "添加字符串"}
        ok, fail = do_rename(d, items, tag_map.get(mode, mode))
        messagebox.showinfo("完成",
            f"执行完成\n成功: {ok} 个\n失败: {fail} 个")
        self.t2_status.set(f"✅ 执行完成 — 成功 {ok} 个，失败 {fail} 个")
        log(f"[功能2-执行] 目录={d}  模式={mode}  成功={ok}  失败={fail}")
        self._t2_preview()

    # ── 配置 & 日志 ────────────────────────────
    def _save_params(self):
        self.cfg.update({
            "t1_dir"         : self.t1_dir.get(),
            "t1_x"           : self.t1_x.get(),
            "t2_dir"         : self.t2_dir.get(),
            "t2_mode"        : self.t2_mode.get(),
            "t2_only_changed": self.t2_only_changed.get(),
            "t2_img_only"    : self.t2_img_only.get(),
            "t2_add_text"    : self.t2_add_text.get(),
            "t2_add_pos"     : self.t2_add_pos.get(),
            "last_run"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_cfg(self.cfg)
        log(f"参数已保存: {self.cfg}")

    def _restore_cfg(self):
        self.t1_dir.set(self.cfg.get("t1_dir", ""))
        self.t1_x.set(self.cfg.get("t1_x", 2))
        self.t2_dir.set(self.cfg.get("t2_dir", ""))
        self.t2_mode.set(self.cfg.get("t2_mode", "to_head"))
        self.t2_add_text.set(self.cfg.get("t2_add_text", ""))
        self.t2_add_pos.set(self.cfg.get("t2_add_pos", "head"))
        self._t2_on_mode_change()

    def _open_log(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            messagebox.showinfo("日志", "日志文件尚未生成")


# ─────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
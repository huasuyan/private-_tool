"""
FileToolkit  v1.0  —  文件工具箱（整合版）
整合自：File manager tool.py / Folder_renamer.py / File_cleaner.py /
        md_restructure.py / Copy structure.py / Webp_to_video.py

依赖（基础功能仅需标准库）：
  Webp转视频额外需要：pip install pillow  +  系统安装 ffmpeg
"""

# ── DPI 感知（必须在 tkinter 之前） ────────────────
import ctypes, sys, os, platform
try:
    if platform.system() == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import re, threading, time, shutil, fnmatch, json, struct, tempfile, subprocess
from pathlib import Path
from datetime import datetime

# ── 可选依赖 ────────────────────────────────────────
try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── DPI 缩放 ────────────────────────────────────────
def _dpi_scale():
    try:
        if platform.system() == "Windows":
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return max(1.0, dpi / 96.0)
    except Exception: pass
    return 1.0

SCALE = _dpi_scale()

def s(v):   return max(1, int(v * SCALE))
def sf(v):  return max(8, int(v * SCALE))

# ══════════════════════════════════════════════════════
#  颜色 / 字体
# ══════════════════════════════════════════════════════
BG      = "#0f1117"
BG2     = "#1a1d27"
BG3     = "#252836"
PANEL   = "#1e2130"
BORDER  = "#2f3440"
ACCENT  = "#6c63ff"
ACCENT2 = "#5a52d8"
SUCCESS = "#34d399"
WARNING = "#fbbf24"
DANGER  = "#f87171"
TEXT    = "#e8e8f0"
TEXT2   = "#7a7a99"
MONO    = ("Consolas",  sf(9))
UI      = ("Segoe UI",  sf(10))
UIS     = ("Segoe UI",  sf(9))
UIB     = ("Segoe UI",  sf(10), "bold")
H1      = ("Segoe UI",  sf(14), "bold")
H2      = ("Segoe UI",  sf(10), "bold")
H3      = ("Segoe UI",  sf(11), "bold")

IMG_EXTS = {".jpg",".jpeg",".png",".webp",".bmp",".gif",
            ".tiff",".tif",".ico",".heic",".heif",".avif",
            ".svg",".raw",".cr2",".nef",".arw",".dng",
            ".jfif",".pjpeg",".pjp"}


# ══════════════════════════════════════════════════════
#  通用 UI 组件
# ══════════════════════════════════════════════════════
def card(parent, **kw):
    return tk.Frame(parent, bg=PANEL,
                    highlightbackground=BORDER, highlightthickness=1, **kw)

class HBtn(tk.Button):
    """悬停变色按钮"""
    def __init__(self, master, hbg=ACCENT2, **kw):
        self._n = kw.get("bg", ACCENT)
        self._h = hbg
        super().__init__(master, relief="flat", bd=0, cursor="hand2", **kw)
        self.bind("<Enter>", lambda e: self.config(bg=self._h))
        self.bind("<Leave>", lambda e: self.config(bg=self._n))

class LogBox(tk.Frame):
    """带颜色标签的日志区域"""
    TAGS = {"ok": SUCCESS, "warn": WARNING, "err": DANGER,
            "info": ACCENT, "dim": TEXT2}

    def __init__(self, parent, height=10, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        self.txt = tk.Text(self, bg=BG3, fg=TEXT, font=MONO,
                           bd=0, relief="flat", state="disabled",
                           highlightthickness=0, wrap="none", height=height)
        self.txt.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.txt.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.txt.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        for tag, col in self.TAGS.items():
            self.txt.tag_config(tag, foreground=col)

    def write(self, msg, tag="info"):
        ts = time.strftime("%H:%M:%S")
        self.txt.configure(state="normal")
        self.txt.insert("end", f"[{ts}] {msg}\n", tag)
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def clear(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

def entry_row(parent, label, var, row, browse_dir=False, browse_save=False,
              filetypes=None, bg=PANEL):
    """标准路径输入行"""
    tk.Label(parent, text=label, bg=bg, fg=TEXT2, font=UIS,
             width=16, anchor="w").grid(row=row, column=0, sticky="w",
                                         padx=(12, 6), pady=5)
    ef = tk.Frame(parent, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
    ef.grid(row=row, column=1, sticky="ew", padx=(0,8), pady=5)
    tk.Entry(ef, textvariable=var, bg=BG3, fg=TEXT,
             insertbackground=TEXT, relief="flat", font=UI, bd=6
             ).pack(fill="x")
    if browse_dir:
        HBtn(parent, text="浏览", bg=BORDER, hbg=ACCENT2, fg=TEXT,
             font=UIS, padx=10, pady=5,
             command=lambda: var.set(filedialog.askdirectory() or var.get())
             ).grid(row=row, column=2, padx=(0,12), pady=5)
    if browse_save:
        def _save():
            p = filedialog.asksaveasfilename(
                defaultextension=filetypes[0][1] if filetypes else ".mp4",
                filetypes=filetypes or [("所有文件","*.*")])
            if p: var.set(p)
        HBtn(parent, text="另存为", bg=BORDER, hbg=ACCENT2, fg=TEXT,
             font=UIS, padx=10, pady=5,
             command=_save).grid(row=row, column=2, padx=(0,12), pady=5)


# ══════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════
class App:
    def __init__(self, root):
        self.root = root
        root.title("FileToolkit  —  文件工具箱")
        root.configure(bg=BG)
        root.minsize(s(800), s(560))
        root.geometry(f"{s(1060)}x{s(740)}")
        try: root.tk.call("tk", "scaling", SCALE * 1.25)
        except Exception: pass

        self._build_styles()
        self._build_ui()

    # ── ttk 样式 ──────────────────────────────────────
    def _build_styles(self):
        s_ = ttk.Style()
        s_.theme_use("clam")
        s_.configure("TNotebook", background=BG, tabmargins=[0,0,0,0])
        s_.configure("TNotebook.Tab", background=BG3, foreground=TEXT2,
                     padding=[s(18), s(9)], font=UIB)
        s_.map("TNotebook.Tab",
               background=[("selected", ACCENT), ("active", BG2)],
               foreground=[("selected", "#fff"),  ("active", TEXT)])
        s_.configure("Bar.Horizontal.TProgressbar",
                     background=ACCENT, troughcolor=BORDER,
                     borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT)
        s_.configure("Vertical.TScrollbar", background=BG3,
                     troughcolor=BG, arrowcolor=TEXT2, borderwidth=0)
        s_.configure("Horizontal.TScrollbar", background=BG3,
                     troughcolor=BG, arrowcolor=TEXT2, borderwidth=0)

    # ── 整体布局 ──────────────────────────────────────
    def _build_ui(self):
        # 顶部 header
        hdr = tk.Frame(self.root, bg=BG, pady=s(8))
        hdr.pack(fill="x", padx=s(16))
        tk.Label(hdr, text="🗂", bg=BG, fg=ACCENT,
                 font=("Segoe UI", sf(20))).pack(side="left", padx=(0, s(8)))
        tk.Label(hdr, text="FileToolkit", bg=BG, fg=TEXT, font=H1).pack(side="left")
        tk.Label(hdr, text="文件工具箱", bg=BG, fg=TEXT2, font=UIS).pack(side="left", padx=s(8))
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=s(16))

        # 选项卡
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=s(16), pady=s(10))

        tabs = [
            ("文件夹重命名", self._build_tab_rename),
            ("文件重命名",   self._build_tab_file_rename),
            ("文件清理",     self._build_tab_cleaner),
            ("Obsidian整理", self._build_tab_obsidian),
            ("目录结构复制", self._build_tab_copy_struct),
            ("WebP转视频",   self._build_tab_webp),
        ]
        for title, builder in tabs:
            f = tk.Frame(nb, bg=BG)
            nb.add(f, text=f"  {title}  ")
            builder(f)


    # ══════════════════════════════════════════════════
    #  Tab 1 — 文件夹重命名
    # ══════════════════════════════════════════════════
    def _build_tab_rename(self, parent):
        parent.columnconfigure(0, weight=3, minsize=s(220))
        parent.columnconfigure(1, weight=2, minsize=s(260))
        parent.rowconfigure(0, weight=1)

        # ── 左：文件夹列表 ──
        lf = tk.Frame(parent, bg=BG)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, s(8)), pady=s(4))
        lf.columnconfigure(0, weight=1); lf.rowconfigure(1, weight=1)

        th = tk.Frame(lf, bg=BG); th.grid(row=0, column=0, sticky="ew", pady=(0, s(4)))
        tk.Label(th, text="待处理文件夹", bg=BG, fg=TEXT, font=H2).pack(side="left")
        self.rn_cnt = tk.Label(th, text="( 0 个 )", bg=BG, fg=TEXT2, font=UIS)
        self.rn_cnt.pack(side="left", padx=s(6))

        lbf = tk.Frame(lf, bg=BORDER, padx=1, pady=1)
        lbf.grid(row=1, column=0, sticky="nsew")
        lbf.rowconfigure(0, weight=1); lbf.columnconfigure(0, weight=1)
        self.rn_lb = tk.Listbox(lbf, bg=PANEL, fg=TEXT,
                                 selectbackground=ACCENT, selectforeground="#fff",
                                 font=MONO, bd=0, highlightthickness=0,
                                 activestyle="none", relief="flat")
        self.rn_lb.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(lbf, orient="vertical", command=self.rn_lb.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(lbf, orient="horizontal", command=self.rn_lb.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.rn_lb.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        bb = tk.Frame(lf, bg=BG); bb.grid(row=2, column=0, sticky="ew", pady=(s(5), 0))
        btns = [
            ("＋ 选择文件夹", ACCENT,   ACCENT2, "white",  self._rn_add_single),
            ("📂 导入子目录", "#1e3a1e","#1a501a",SUCCESS, self._rn_add_parent),
            ("✕ 移除选中",   "#2e1e1e","#3d2020",DANGER,  self._rn_remove),
            ("清空",          PANEL,    BORDER,  TEXT2,   self._rn_clear),
        ]
        for txt, bg, hbg, fg, cmd in btns:
            HBtn(bb, text=txt, bg=bg, hbg=hbg, fg=fg,
                 font=UIS, padx=s(8), pady=s(4),
                 command=cmd).pack(side="left", padx=(0, s(3)))

        # ── 右：设置+进度+日志 ──
        rf = tk.Frame(parent, bg=BG)
        rf.grid(row=0, column=1, sticky="nsew", pady=s(4))
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(2, weight=1)

        # 设置卡
        c = card(rf, padx=s(12), pady=s(10))
        c.grid(row=0, column=0, sticky="ew", pady=(0, s(5)))
        c.columnconfigure(0, weight=1)
        tk.Label(c, text="删除模式", bg=PANEL, fg=TEXT2, font=UIS).pack(anchor="w", pady=(0,s(4)))

        self.rn_mode = tk.StringVar(value="fixed")
        mr = tk.Frame(c, bg=PANEL); mr.pack(fill="x", pady=(0,s(8)))
        mr.columnconfigure(0, weight=1); mr.columnconfigure(1, weight=1)
        self.rn_btn_fix = tk.Button(mr, text="固定字符数", font=UIS,
            bg=BORDER, fg=TEXT2, relief="flat", bd=0, pady=s(7),
            cursor="hand2", command=lambda: self.rn_mode.set("fixed"))
        self.rn_btn_fix.grid(row=0, column=0, sticky="ew", padx=(0, s(3)))
        self.rn_btn_pre = tk.Button(mr, text="数字前缀＋连字符", font=UIS,
            bg=BORDER, fg=TEXT2, relief="flat", bd=0, pady=s(7),
            cursor="hand2", command=lambda: self.rn_mode.set("prefix"))
        self.rn_btn_pre.grid(row=0, column=1, sticky="ew")
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(0,s(8)))

        # 固定字符面板
        self.rn_fix_f = tk.Frame(c, bg=PANEL)
        row_n = tk.Frame(self.rn_fix_f, bg=PANEL); row_n.pack(anchor="w")
        tk.Label(row_n, text="删除前", bg=PANEL, fg=TEXT, font=UI).pack(side="left")
        self.rn_nvar = tk.IntVar(value=2)
        HBtn(row_n, text="−", bg=BORDER, hbg=ACCENT, fg="white",
             font=("Segoe UI", sf(11), "bold"), width=2,
             command=lambda: self._rn_adjn(-1)).pack(side="left", padx=(s(8),s(2)))
        tk.Entry(row_n, textvariable=self.rn_nvar, bg=BG3, fg=TEXT,
                 font=("Consolas", sf(12), "bold"), width=4, justify="center",
                 bd=0, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT, insertbackground=TEXT).pack(side="left", padx=s(2))
        HBtn(row_n, text="＋", bg=BORDER, hbg=ACCENT, fg="white",
             font=("Segoe UI", sf(11), "bold"), width=2,
             command=lambda: self._rn_adjn(1)).pack(side="left", padx=(s(2),s(8)))
        tk.Label(row_n, text="个字符", bg=PANEL, fg=TEXT, font=UI).pack(side="left")
        self.rn_nvar.trace_add("write", lambda *a: self._rn_preview())

        # 前缀面板
        self._PRE = re.compile(r"^\d+-")
        self.rn_pre_f = tk.Frame(c, bg=PANEL)
        ib = tk.Frame(self.rn_pre_f, bg=BG3,
                      highlightbackground=BORDER, highlightthickness=1)
        ib.pack(fill="x", pady=(0,s(5)))
        tk.Label(ib, text="匹配规则：^\\d+-  （数字串 + 连字符「-」）",
                 bg=BG3, fg=ACCENT, font=MONO).pack(anchor="w", padx=s(8), pady=s(4))
        eg = tk.Frame(ib, bg=BG3); eg.pack(anchor="w", padx=s(8), pady=(0,s(4)))
        for o, r in [("01-项目文档","项目文档"),("123-设计稿","设计稿")]:
            rr = tk.Frame(eg, bg=BG3); rr.pack(anchor="w")
            tk.Label(rr, text=f"{o}  →  ", bg=BG3, fg=TEXT2, font=MONO).pack(side="left")
            tk.Label(rr, text=r, bg=BG3, fg=SUCCESS, font=MONO).pack(side="left")
        nm = tk.Frame(self.rn_pre_f, bg=PANEL); nm.pack(fill="x")
        tk.Label(nm, text="未匹配时：", bg=PANEL, fg=TEXT, font=UI).pack(side="left")
        self.rn_nm = tk.StringVar(value="skip")
        for v, l in [("skip","跳过"), ("keep","保留原名")]:
            tk.Radiobutton(nm, text=l, variable=self.rn_nm, value=v,
                           bg=PANEL, fg=TEXT, selectcolor=BG3,
                           activebackground=PANEL, font=UIS,
                           cursor="hand2").pack(side="left", padx=(s(5),0))
        self.rn_nm.trace_add("write", lambda *a: self._rn_preview())

        # 选项行
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=s(7))
        opt = tk.Frame(c, bg=PANEL); opt.pack(fill="x", pady=(0,s(5)))
        self.rn_skip_hid = tk.BooleanVar(value=True)
        self.rn_dry      = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="跳过隐藏文件夹",
                        variable=self.rn_skip_hid).pack(side="left", padx=(0,s(12)))
        ttk.Checkbutton(opt, text="试运行（不实际重命名）",
                        variable=self.rn_dry).pack(side="left")

        # 预览
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(0,s(5)))
        tk.Label(c, text="重命名预览", bg=PANEL, fg=TEXT2, font=UIS).pack(anchor="w", pady=(0,s(2)))
        self.rn_pvw = tk.Label(c,
            text="─ 在左侧选中一个文件夹查看预览 ─",
            bg=BG3, fg=ACCENT, font=MONO, anchor="w", justify="left",
            padx=s(8), pady=s(5),
            highlightbackground=BORDER, highlightthickness=1)
        self.rn_pvw.pack(fill="x")

        # 进度卡
        pc = card(rf, padx=s(12), pady=s(8))
        pc.grid(row=1, column=0, sticky="ew", pady=(0, s(5)))
        pr = tk.Frame(pc, bg=PANEL); pr.pack(fill="x", pady=(0,s(5)))
        tk.Label(pr, text="执行进度", bg=PANEL, fg=TEXT, font=H2).pack(side="left")
        self.rn_plbl = tk.Label(pr, text="就绪", bg=PANEL, fg=TEXT2, font=UIS)
        self.rn_plbl.pack(side="right")
        self.rn_pvar = tk.DoubleVar(value=0)
        ttk.Progressbar(pc, variable=self.rn_pvar, maximum=100,
                         style="Bar.Horizontal.TProgressbar").pack(fill="x", pady=(0,s(5)))
        sr = tk.Frame(pc, bg=PANEL); sr.pack(fill="x")
        sr.columnconfigure(0,weight=1); sr.columnconfigure(1,weight=1); sr.columnconfigure(2,weight=1)
        self.rn_s_done = self._statbox(sr, "完成", SUCCESS, 0)
        self.rn_s_skip = self._statbox(sr, "跳过", WARNING, 1)
        self.rn_s_fail = self._statbox(sr, "失败", DANGER,  2)

        # 日志卡
        lc = card(rf, padx=s(12), pady=s(8))
        lc.grid(row=2, column=0, sticky="nsew")
        lc.rowconfigure(1, weight=1); lc.columnconfigure(0, weight=1)
        hr2 = tk.Frame(lc, bg=PANEL); hr2.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,s(4)))
        tk.Label(hr2, text="执行日志", bg=PANEL, fg=TEXT, font=H2).pack(side="left")
        HBtn(hr2, text="清除", bg=PANEL, hbg=BORDER, fg=TEXT2, font=UIS,
             padx=s(6), pady=s(2),
             command=lambda: self.rn_log.clear()).pack(side="right")
        self.rn_log = LogBox(lc, height=6)
        self.rn_log.grid(row=1, column=0, sticky="nsew")
        vsb2 = ttk.Scrollbar(lc, orient="vertical")
        vsb2.grid(row=1, column=1, sticky="ns")

        # 底部执行栏
        bot = tk.Frame(parent, bg=BG, pady=s(6))
        bot.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.rn_status = tk.Label(bot, text="✦  准备就绪",
                                   bg=BG, fg=TEXT2, font=UIS)
        self.rn_status.pack(side="left")
        self.rn_stop_btn = HBtn(bot, text="⏹  停止",
            bg=BG, hbg="#2a1a1a", fg=DANGER, font=UI,
            padx=s(10), pady=s(5), state="disabled",
            command=self._rn_stop)
        self.rn_stop_btn.pack(side="right", padx=(s(5),0))
        self.rn_run_btn = HBtn(bot, text="▶  开始重命名",
            bg=ACCENT, hbg=ACCENT2, fg="white",
            font=H3, padx=s(16), pady=s(5), command=self._rn_start)
        self.rn_run_btn.pack(side="right")

        # 初始化
        self.rn_folders = []; self.rn_running = False; self.rn_stop_flag = False
        self.rn_lb.bind("<<ListboxSelect>>", self._rn_preview)
        self.rn_mode.trace_add("write", lambda *a: self._rn_on_mode())
        self._rn_on_mode()

    def _statbox(self, parent, lbl, color, col):
        f = tk.Frame(parent, bg=BORDER, padx=s(6), pady=s(4))
        f.grid(row=0, column=col, sticky="ew", padx=(0,s(3)) if col<2 else 0)
        v = tk.Label(f, text="0", bg=BORDER, fg=color,
                     font=("Segoe UI", sf(14), "bold"))
        v.pack(); tk.Label(f, text=lbl, bg=BORDER, fg=TEXT2, font=UIS).pack()
        return v

    def _rn_on_mode(self):
        m = self.rn_mode.get()
        if m == "fixed":
            self.rn_btn_fix.config(bg=ACCENT, fg="white")
            self.rn_btn_pre.config(bg=BORDER, fg=TEXT2)
            self.rn_pre_f.pack_forget(); self.rn_fix_f.pack(fill="x")
        else:
            self.rn_btn_pre.config(bg=ACCENT, fg="white")
            self.rn_btn_fix.config(bg=BORDER, fg=TEXT2)
            self.rn_fix_f.pack_forget(); self.rn_pre_f.pack(fill="x")
        self._rn_preview()

    def _rn_add_single(self):
        d = filedialog.askdirectory(title="选择文件夹", mustexist=True)
        if d: self._rn_bulk([Path(d)])

    def _rn_add_parent(self):
        d = filedialog.askdirectory(title="选择父文件夹（导入所有直接子文件夹）")
        if not d: return
        ch = [c for c in Path(d).iterdir() if c.is_dir()]
        if not ch: messagebox.showinfo("提示","该文件夹下没有子文件夹"); return
        self._rn_bulk(ch)
        self.rn_log.write(f"从 {Path(d).name} 导入 {len(ch)} 个子文件夹")

    def _rn_bulk(self, paths):
        n = 0
        for p in paths:
            if p not in self.rn_folders:
                self.rn_folders.append(p)
                self.rn_lb.insert("end", str(p)); n+=1
        self.rn_cnt.config(text=f"( {len(self.rn_folders)} 个 )")
        self._rn_preview()

    def _rn_remove(self):
        for i in reversed(self.rn_lb.curselection()):
            self.rn_lb.delete(i); del self.rn_folders[i]
        self.rn_cnt.config(text=f"( {len(self.rn_folders)} 个 )")
        self._rn_preview()

    def _rn_clear(self):
        if self.rn_folders and messagebox.askyesno("确认","清空列表？"):
            self.rn_folders.clear(); self.rn_lb.delete(0,"end")
            self.rn_cnt.config(text="( 0 个 )"); self._rn_preview()

    def _rn_new_name(self, name):
        if self.rn_mode.get() == "fixed":
            try: n = self.rn_nvar.get()
            except: n=0
            return None if n<=0 or n>=len(name) else name[n:]
        else:
            m = self._PRE.match(name)
            if not m: return name if self.rn_nm.get()=="keep" else None
            return name[m.end():]

    def _rn_preview(self, _=None):
        sel = self.rn_lb.curselection()
        name = (self.rn_folders[sel[0]].name if sel
                else (self.rn_folders[0].name if self.rn_folders else None))
        if not name:
            self.rn_pvw.config(text="─ 在左侧选中一个文件夹查看预览 ─"); return
        if self.rn_mode.get() == "fixed":
            try: n = self.rn_nvar.get()
            except: n=0
            if 0 < n < len(name):
                self.rn_pvw.config(text=f"原名:  {name}\n删前:  {'─'*n}{name[n:]}\n新名:  {name[n:]}")
            else: self.rn_pvw.config(text=f"原名:  {name}\n状态:  名称过短或 N 无效")
        else:
            m = self._PRE.match(name)
            if m: self.rn_pvw.config(text=f"原名:  {name}\n前缀:  「{name[:m.end()]}」\n新名:  {name[m.end():]}")
            else:
                act = "保留原名" if self.rn_nm.get()=="keep" else "跳过"
                self.rn_pvw.config(text=f"原名:  {name}\n匹配:  无数字-前缀\n操作:  {act}")

    def _rn_adjn(self, d):
        try: self.rn_nvar.set(max(1, self.rn_nvar.get()+d))
        except: self.rn_nvar.set(1)

    def _rn_start(self):
        if not self.rn_folders:
            messagebox.showwarning("提示","请先添加要处理的文件夹"); return
        if self.rn_mode.get()=="fixed":
            try: n=self.rn_nvar.get(); assert n>0
            except: messagebox.showerror("错误","请输入有效正整数"); return
        if not self.rn_dry.get():
            if not messagebox.askyesno("确认操作",
                f"将对 {len(self.rn_folders)} 个文件夹执行重命名\n此操作不可撤销，是否继续？"):
                return
        self.rn_running=True; self.rn_stop_flag=False
        self.rn_run_btn.config(state="disabled")
        self.rn_stop_btn.config(state="normal")
        self.rn_s_done.config(text="0"); self.rn_s_skip.config(text="0")
        self.rn_s_fail.config(text="0"); self.rn_pvar.set(0)
        self.rn_log.write(f"开始 · {len(self.rn_folders)} 个文件夹", "info")
        threading.Thread(target=self._rn_run, daemon=True).start()

    def _rn_run(self):
        total=len(self.rn_folders); done=skip=fail=0; dry=self.rn_dry.get()
        renamed={}
        for i, folder in enumerate(self.rn_folders):
            if self.rn_stop_flag:
                self.root.after(0, self.rn_log.write, "⏹ 用户终止", "warn"); break
            pct=i/total*100
            self.root.after(0, self.rn_pvar.set, pct)
            self.root.after(0, self.rn_plbl.config, {"text":f"{i+1}/{total}"})
            name=folder.name; par=folder.parent
            if self.rn_skip_hid.get() and name.startswith("."):
                skip+=1; self.root.after(0, self.rn_log.write, f"跳过隐藏: {name}", "warn")
                self.root.after(0, self.rn_s_skip.config, {"text":str(skip)})
                self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":WARNING})); continue
            nn=self._rn_new_name(name)
            if nn is None:
                skip+=1; r="名称过短" if self.rn_mode.get()=="fixed" else "无匹配前缀"
                self.root.after(0, self.rn_log.write, f"跳过({r}): {name}", "warn")
                self.root.after(0, self.rn_s_skip.config, {"text":str(skip)})
                self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":WARNING})); continue
            if nn==name:
                skip+=1; self.root.after(0, self.rn_log.write, f"保留原名: {name}", "warn")
                self.root.after(0, self.rn_s_skip.config, {"text":str(skip)})
                self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":WARNING})); continue
            np=par/nn
            if np.exists():
                fail+=1; self.root.after(0, self.rn_log.write, f"冲突: {name} → {nn}", "err")
                self.root.after(0, self.rn_s_fail.config, {"text":str(fail)})
                self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":DANGER})); continue
            if dry:
                done+=1; self.root.after(0, self.rn_log.write, f"[试] {name} → {nn}", "ok")
                self.root.after(0, self.rn_s_done.config, {"text":str(done)})
                self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":SUCCESS}))
            else:
                try:
                    folder.rename(np); renamed[folder]=np; done+=1
                    self.root.after(0, self.rn_log.write, f"✓ {name} → {nn}", "ok")
                    self.root.after(0, self.rn_s_done.config, {"text":str(done)})
                    self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":SUCCESS}))
                except Exception as e:
                    fail+=1; self.root.after(0, self.rn_log.write, f"✗ {name}  {e}", "err")
                    self.root.after(0, self.rn_s_fail.config, {"text":str(fail)})
                    self.root.after(0, lambda i=i: self.rn_lb.itemconfig(i,{"fg":DANGER}))
            time.sleep(0.001)
        self.root.after(0, self.rn_pvar.set, 100)
        s_ = f"完成 {done} · 跳过 {skip} · 失败 {fail}"
        self.root.after(0, self.rn_plbl.config, {"text":s_})
        self.root.after(0, self.rn_log.write, s_, "info")
        self.root.after(0, self.rn_status.config, {"text":f"✦  {s_}", "fg":SUCCESS})
        self.root.after(0, self.rn_run_btn.config, {"state":"normal"})
        self.root.after(0, self.rn_stop_btn.config, {"state":"disabled"})
        if not dry and renamed:
            self.root.after(200, self._rn_refresh, renamed)
        self.rn_running=False

    def _rn_refresh(self, renamed):
        self.rn_lb.delete(0,"end"); nf=[]
        for p in self.rn_folders:
            np=renamed.get(p,p)
            if not np.exists() and p.exists(): np=p
            nf.append(np); self.rn_lb.insert("end",str(np))
        self.rn_folders=nf

    def _rn_stop(self):
        self.rn_stop_flag=True
        self.rn_status.config(text="⏹  正在停止…", fg=WARNING)


    # ══════════════════════════════════════════════════
    #  Tab 2 — 文件重命名（括号整理 / 添加字符串）
    # ══════════════════════════════════════════════════
    _BRACKET_RE = re.compile(r"(【[^】]*】)")

    def _build_tab_file_rename(self, parent):
        parent.columnconfigure(0, weight=1); parent.rowconfigure(1, weight=1)

        # 设置卡
        c = card(parent, padx=s(14), pady=s(12))
        c.grid(row=0, column=0, sticky="ew", padx=s(8), pady=(s(8),s(4)))
        c.columnconfigure(1, weight=1)

        tk.Label(c, text="目标目录", bg=PANEL, fg=TEXT2, font=UIS
                 ).grid(row=0, column=0, sticky="w", padx=(0,s(8)), pady=s(5))
        self.fr_dir = tk.StringVar()
        ef = tk.Frame(c, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        ef.grid(row=0, column=1, sticky="ew", pady=s(5))
        tk.Entry(ef, textvariable=self.fr_dir, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=UI, bd=6).pack(fill="x")
        HBtn(c, text="浏览", bg=BORDER, hbg=ACCENT2, fg=TEXT, font=UIS,
             padx=s(10), pady=s(5),
             command=lambda: self.fr_dir.set(filedialog.askdirectory() or self.fr_dir.get())
             ).grid(row=0, column=2, padx=(s(8),0), pady=s(5))

        # 模式选择
        tk.Label(c, text="操作模式", bg=PANEL, fg=TEXT2, font=UIS
                 ).grid(row=1, column=0, sticky="w", padx=(0,s(8)), pady=(s(8),s(4)))
        self.fr_mode = tk.StringVar(value="to_head")
        mf = tk.Frame(c, bg=PANEL); mf.grid(row=1, column=1, columnspan=2, sticky="w")
        self.fr_mode_btns = {}
        MODES = [("to_head","【】移至开头"),("to_tail","【】移至末尾"),
                 ("delete","删除【】内容"),("add_str","添加字符串")]
        for val, lbl in MODES:
            b = tk.Button(mf, text=lbl, font=UIS, bg=BG3, fg=TEXT2,
                          relief="flat", bd=1, padx=s(12), pady=s(5), cursor="hand2",
                          command=lambda v=val: self._fr_set_mode(v))
            b.pack(side="left", padx=(0,s(4))); self.fr_mode_btns[val]=b

        # 添加字符串子面板
        self.fr_add_f = tk.Frame(c, bg=PANEL)
        self.fr_add_f.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(s(4),0))
        tk.Label(self.fr_add_f, text="添加文本", bg=PANEL, fg=TEXT, font=UI
                 ).pack(side="left", padx=(0,s(6)))
        self.fr_add_text = tk.StringVar()
        aef = tk.Frame(self.fr_add_f, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        aef.pack(side="left")
        tk.Entry(aef, textvariable=self.fr_add_text, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=UI, bd=5, width=20).pack()
        tk.Label(self.fr_add_f, text="位置：", bg=PANEL, fg=TEXT, font=UI
                 ).pack(side="left", padx=(s(12),s(4)))
        self.fr_add_pos = tk.StringVar(value="head")
        for v,l in [("head","开头"),("tail","末尾")]:
            tk.Radiobutton(self.fr_add_f, text=l, variable=self.fr_add_pos, value=v,
                           bg=PANEL, fg=TEXT, selectcolor=BG3,
                           activebackground=PANEL, font=UIS, cursor="hand2"
                           ).pack(side="left", padx=(0,s(8)))

        # 过滤选项
        opt = tk.Frame(c, bg=PANEL)
        opt.grid(row=3, column=0, columnspan=3, sticky="w", pady=(s(8),0))
        self.fr_img_only     = tk.BooleanVar(value=True)
        self.fr_only_changed = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="仅处理图片格式", variable=self.fr_img_only
                        ).pack(side="left", padx=(0,s(14)))
        ttk.Checkbutton(opt, text="仅预览需修改项", variable=self.fr_only_changed
                        ).pack(side="left")

        # 按钮行
        br = tk.Frame(c, bg=PANEL); br.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(s(10),s(2)))
        HBtn(br, text="🔍 预览", bg=ACCENT, hbg=ACCENT2, fg="white",
             font=UIB, padx=s(14), pady=s(6), command=self._fr_preview
             ).pack(side="left", padx=(0,s(8)))
        HBtn(br, text="☑ 全选", bg=BORDER, hbg=BG3, fg=TEXT, font=UIS,
             padx=s(10), pady=s(6), command=lambda: self._fr_select_all(True)
             ).pack(side="left", padx=(0,s(4)))
        HBtn(br, text="☐ 全不选", bg=BORDER, hbg=BG3, fg=TEXT, font=UIS,
             padx=s(10), pady=s(6), command=lambda: self._fr_select_all(False)
             ).pack(side="left", padx=(0,s(4)))
        HBtn(br, text="✅ 执行重命名", bg="#1e3a1e", hbg="#1a501a", fg=SUCCESS,
             font=UIB, padx=s(14), pady=s(6), command=self._fr_execute
             ).pack(side="right")

        # 表格区
        tf = card(parent, padx=s(4), pady=s(4))
        tf.grid(row=1, column=0, sticky="nsew", padx=s(8), pady=(0,s(8)))
        tf.rowconfigure(1, weight=1); tf.columnconfigure(0, weight=1)

        # 表头
        hdr = tk.Frame(tf, bg=BG3); hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        for txt, w in [("✓",3),("原文件名",38),("→",4),("新文件名",38),("状态",12)]:
            tk.Label(hdr, text=txt, bg=BG3, fg=ACCENT, font=H2,
                     width=w, anchor="w").pack(side="left", padx=s(4), pady=s(4))

        # 滚动表格
        self.fr_canvas = tk.Canvas(tf, bg=PANEL, highlightthickness=0)
        self.fr_canvas.grid(row=1, column=0, sticky="nsew")
        vsb3 = ttk.Scrollbar(tf, orient="vertical", command=self.fr_canvas.yview)
        vsb3.grid(row=1, column=1, sticky="ns")
        self.fr_canvas.configure(yscrollcommand=vsb3.set)
        self.fr_inner = tk.Frame(self.fr_canvas, bg=PANEL)
        self.fr_win = self.fr_canvas.create_window((0,0), window=self.fr_inner, anchor="nw")
        self.fr_inner.bind("<Configure>",
            lambda e: self.fr_canvas.configure(scrollregion=self.fr_canvas.bbox("all")))
        self.fr_canvas.bind("<Configure>",
            lambda e: self.fr_canvas.itemconfig(self.fr_win, width=e.width))
        self.fr_canvas.bind("<MouseWheel>",
            lambda e: self.fr_canvas.yview_scroll(-1*(e.delta//120), "units"))

        # 状态栏
        self.fr_status = tk.Label(parent, text="请先选择目录并点击「预览」",
                                   bg=BG, fg=TEXT2, font=UIS, anchor="w")
        self.fr_status.grid(row=2, column=0, sticky="ew", padx=s(10), pady=(0,s(4)))

        self.fr_items=[]; self.fr_vars=[]
        self._fr_set_mode("to_head")

    def _fr_set_mode(self, val):
        self.fr_mode.set(val)
        for v,b in self.fr_mode_btns.items():
            b.config(bg=ACCENT if v==val else BG3, fg="white" if v==val else TEXT2)
        state = "normal" if val=="add_str" else "disabled"
        for w in self.fr_add_f.winfo_children():
            try: w.config(state=state)
            except: pass

    def _fr_get_names(self):
        d=self.fr_dir.get().strip()
        if not d or not os.path.isdir(d): return []
        files=sorted([f for f in os.listdir(d) if os.path.isfile(os.path.join(d,f))])
        if self.fr_img_only.get():
            files=[f for f in files if Path(f).suffix.lower() in IMG_EXTS]
        return files

    def _fr_build_items(self, names):
        mode=self.fr_mode.get()
        result=[]
        for name in names:
            stem,suffix=Path(name).stem, Path(name).suffix
            brackets=self._BRACKET_RE.findall(stem)
            if mode=="to_head":
                if brackets:
                    new=("".join(brackets)+self._BRACKET_RE.sub("",stem))+suffix
                    result.append({"original":name,"new_name":new,"changed":new!=name,"valid":True,"has_bracket":True})
                else: result.append({"original":name,"new_name":name,"changed":False,"valid":True,"has_bracket":False})
            elif mode=="to_tail":
                if brackets:
                    new=(self._BRACKET_RE.sub("",stem)+"".join(brackets))+suffix
                    result.append({"original":name,"new_name":new,"changed":new!=name,"valid":True,"has_bracket":True})
                else: result.append({"original":name,"new_name":name,"changed":False,"valid":True,"has_bracket":False})
            elif mode=="delete":
                if brackets:
                    ns=self._BRACKET_RE.sub("",stem).strip()
                    valid=bool(ns); new=(ns+suffix) if valid else ""
                    result.append({"original":name,"new_name":new,"changed":name!=new if valid else True,"valid":valid,"has_bracket":True})
                else: result.append({"original":name,"new_name":name,"changed":False,"valid":True,"has_bracket":False})
            else:  # add_str
                text=self.fr_add_text.get()
                if text:
                    new=(text+stem+suffix) if self.fr_add_pos.get()=="head" else (stem+text+suffix)
                    result.append({"original":name,"new_name":new,"changed":True,"valid":True,"has_bracket":False})
                else: result.append({"original":name,"new_name":name,"changed":False,"valid":True,"has_bracket":False})
        return result

    def _fr_preview(self):
        d=self.fr_dir.get().strip()
        if not d or not os.path.isdir(d):
            messagebox.showwarning("提示","请选择有效目录"); return
        if self.fr_mode.get()=="add_str" and not self.fr_add_text.get().strip():
            messagebox.showwarning("提示","请先填写要添加的文本"); return
        names=self._fr_get_names()
        if not names:
            self.fr_status.config(text="⚠ 该目录下没有找到文件"); return
        items=self._fr_build_items(names)
        total=len(items)
        for item in items: item["selected"]=item.get("changed",False)
        if self.fr_only_changed.get():
            items=[i for i in items if i.get("changed")]
        self.fr_items=items; self.fr_vars=[]
        for w in self.fr_inner.winfo_children(): w.destroy()
        for idx,item in enumerate(items):
            bg=BG3 if idx%2==0 else PANEL
            row=tk.Frame(self.fr_inner,bg=bg); row.pack(fill="x")
            var=tk.BooleanVar(value=item.get("selected",True))
            self.fr_vars.append(var); item["_var"]=var
            tk.Checkbutton(row, variable=var, bg=bg, fg=TEXT,
                           activebackground=bg, selectcolor=BG3,
                           relief="flat", bd=0, cursor="hand2"
                           ).pack(side="left", padx=s(6), pady=s(3))
            old,new=item["original"],item["new_name"]
            oc=TEXT if item.get("changed") else TEXT2
            nc=SUCCESS if item.get("changed") else TEXT2
            st="✓ 将重命名" if item.get("changed") and item.get("valid") else ("⚠ 结果为空" if not item.get("valid") else "— 无需修改")
            sc=SUCCESS if item.get("changed") and item.get("valid") else (DANGER if not item.get("valid") else TEXT2)
            tk.Label(row,text=old,bg=bg,fg=oc,font=MONO,width=38,anchor="w").pack(side="left",padx=s(2))
            tk.Label(row,text="→",bg=bg,fg=TEXT2,font=UI).pack(side="left")
            tk.Label(row,text=new,bg=bg,fg=nc,font=MONO,width=38,anchor="w").pack(side="left",padx=s(2))
            tk.Label(row,text=st,bg=bg,fg=sc,font=UIS,width=12).pack(side="left",padx=s(4))
        changed_n=sum(1 for i in items if i.get("changed"))
        self.fr_status.config(text=f"共扫描 {total} 个文件，{changed_n} 个将被修改（显示 {len(items)} 项）")

    def _fr_select_all(self, state):
        for v in self.fr_vars: v.set(state)

    def _fr_execute(self):
        if not self.fr_items: messagebox.showinfo("提示","请先点击「预览」"); return
        d=self.fr_dir.get().strip()
        sel=[i for i in self.fr_items if i.get("_var") and i["_var"].get() and i.get("changed") and i.get("valid")]
        if not sel: messagebox.showinfo("提示","没有选中任何需修改的文件"); return
        if not messagebox.askyesno("确认",f"即将重命名 {len(sel)} 个文件，是否继续？"): return
        ok=fail=0
        for item in sel:
            src=os.path.join(d,item["original"]); dst=os.path.join(d,item["new_name"])
            try:
                if os.path.exists(dst): raise FileExistsError(f"目标已存在")
                os.rename(src,dst); ok+=1
            except Exception as e: fail+=1
        messagebox.showinfo("完成",f"成功: {ok} 个\n失败: {fail} 个")
        self._fr_preview()


    # ══════════════════════════════════════════════════
    #  Tab 3 — 文件清理
    # ══════════════════════════════════════════════════
    def _build_tab_cleaner(self, parent):
        parent.columnconfigure(0, weight=1); parent.rowconfigure(1, weight=1)

        c = card(parent, padx=s(14), pady=s(12))
        c.grid(row=0, column=0, sticky="ew", padx=s(8), pady=(s(8),s(4)))
        c.columnconfigure(1, weight=1)

        # 目录
        self.cl_dir = tk.StringVar()
        entry_row(c, "目标目录", self.cl_dir, 0, browse_dir=True)

        # 文件名/通配符输入
        tk.Label(c, text="文件名/通配符", bg=PANEL, fg=TEXT2, font=UIS, width=16, anchor="w"
                 ).grid(row=1, column=0, sticky="w", padx=(0,s(8)), pady=s(5))
        inp_f = tk.Frame(c, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        inp_f.grid(row=1, column=1, sticky="ew", pady=s(5))
        self.cl_input = tk.StringVar()
        self.cl_entry = tk.Entry(inp_f, textvariable=self.cl_input, bg=BG3, fg=TEXT,
                                  insertbackground=TEXT, relief="flat", font=UI, bd=6)
        self.cl_entry.pack(fill="x")
        self.cl_entry.bind("<Return>", lambda e: self._cl_add())
        HBtn(c, text="＋ 添加", bg=ACCENT, hbg=ACCENT2, fg="white", font=UIS,
             padx=s(10), pady=s(5), command=self._cl_add).grid(row=1, column=2, padx=(s(8),0), pady=s(5))
        tk.Label(c, text="支持精确文件名（如 .DS_Store）或通配符（如 *.log）",
                 bg=PANEL, fg=TEXT2, font=("Segoe UI",sf(8))).grid(
                     row=2, column=0, columnspan=3, sticky="w", padx=(0,0), pady=(0,s(4)))

        # 标签区
        self.cl_tag_f = tk.Frame(c, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        self.cl_tag_f.grid(row=3, column=0, columnspan=3, sticky="ew", padx=0, pady=(0,s(8)))
        self.cl_tags = []
        self.cl_empty_lbl = tk.Label(self.cl_tag_f, text="─ 尚未添加文件名 ─",
                                      bg=BG3, fg=TEXT2, font=UIS)
        self.cl_empty_lbl.pack(pady=s(10))

        # 选项
        opt = tk.Frame(c, bg=PANEL); opt.grid(row=4, column=0, columnspan=3, sticky="w")
        self.cl_dry   = tk.BooleanVar(value=True)
        self.cl_confirm = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="模拟运行（不实际删除）", variable=self.cl_dry
                        ).pack(side="left", padx=(0,s(14)))
        ttk.Checkbutton(opt, text="删除前确认", variable=self.cl_confirm
                        ).pack(side="left")

        # 按钮行
        br = tk.Frame(c, bg=PANEL); br.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(s(10),s(2)))
        HBtn(br, text="🔍 扫描预览", bg="#0d3060", hbg="#1056aa", fg="#79C0FF",
             font=UIB, padx=s(14), pady=s(6), command=self._cl_scan).pack(side="left", padx=(0,s(8)))
        self.cl_del_btn = HBtn(br, text="🗑 执行删除", bg="#3a1010", hbg="#6a1e1e",
             fg=DANGER, font=UIB, padx=s(14), pady=s(6), state="disabled",
             command=self._cl_delete)
        self.cl_del_btn.pack(side="left", padx=(0,s(8)))
        HBtn(br, text="清空日志", bg=BORDER, hbg=BG3, fg=TEXT2, font=UIS,
             padx=s(10), pady=s(6), command=lambda: self.cl_log.clear()).pack(side="right")

        # 进度 + 日志
        self.cl_pvar = tk.DoubleVar()
        ttk.Progressbar(parent, variable=self.cl_pvar, maximum=100,
                         style="Bar.Horizontal.TProgressbar",
                         ).grid(row=1, column=0, sticky="ew", padx=s(8), pady=(0,s(4)))
        self.cl_log = LogBox(parent, height=10)
        self.cl_log.grid(row=2, column=0, sticky="nsew", padx=s(8), pady=(0,s(8)))
        parent.rowconfigure(2, weight=1)

        self.cl_scan_results=[]

    def _cl_add(self):
        raw=self.cl_input.get().strip()
        if not raw: return
        names=[n.strip() for n in raw.replace(","," ").split() if n.strip()]
        for name in names:
            if any(t["name"]==name for t in self.cl_tags):
                self.cl_log.write(f"「{name}」已存在", "warn"); continue
            self.cl_tags.append({"name":name})
            self.cl_log.write(f"已添加: {name}", "ok")
        self.cl_input.set("")
        self._cl_refresh_tags()
        self.cl_del_btn.config(state="disabled")
        self.cl_scan_results=[]

    def _cl_refresh_tags(self):
        for w in self.cl_tag_f.winfo_children(): w.destroy()
        if not self.cl_tags:
            self.cl_empty_lbl = tk.Label(self.cl_tag_f, text="─ 尚未添加文件名 ─",
                                          bg=BG3, fg=TEXT2, font=UIS)
            self.cl_empty_lbl.pack(pady=s(10))
            return
        wrap = tk.Frame(self.cl_tag_f, bg=BG3)
        wrap.pack(fill="x", padx=s(4), pady=s(4))
        for tag in self.cl_tags:
            tf2 = tk.Frame(wrap, bg=BG3, highlightbackground=ACCENT, highlightthickness=1)
            tf2.pack(side="left", padx=s(3), pady=s(3))
            tk.Label(tf2, text=tag["name"], bg=BG3, fg=ACCENT, font=MONO,
                     padx=s(6), pady=s(2)).pack(side="left")
            def _rm(t=tag):
                self.cl_tags.remove(t); self._cl_refresh_tags()
                self.cl_del_btn.config(state="disabled"); self.cl_scan_results=[]
            tk.Label(tf2, text="×", bg=BG3, fg=TEXT2, font=UIB,
                     padx=s(4), cursor="hand2").pack(side="left")
            tf2.winfo_children()[-1].bind("<Button-1>", lambda e, r=_rm: r())

    def _cl_scan(self):
        d=self.cl_dir.get().strip()
        if not d or not os.path.isdir(d): messagebox.showwarning("提示","请选择有效目录"); return
        if not self.cl_tags: messagebox.showwarning("提示","请至少添加一个文件名"); return
        self.cl_del_btn.config(state="disabled")
        self.cl_scan_results=[]
        self.cl_log.write(f"开始扫描: {d}", "info")
        patterns=[t["name"] for t in self.cl_tags]
        def worker():
            found=[]
            try:
                for dirpath,_,files in os.walk(d):
                    for f in files:
                        for pat in patterns:
                            if fnmatch.fnmatch(f,pat):
                                found.append(os.path.join(dirpath,f)); break
            except PermissionError as e:
                self.root.after(0, self.cl_log.write, f"权限错误: {e}", "warn")
            self.root.after(0, self._cl_scan_done, found)
        threading.Thread(target=worker, daemon=True).start()

    def _cl_scan_done(self, found):
        self.cl_scan_results=found
        self.cl_log.write(f"扫描完成，共找到 {len(found)} 个匹配文件", "info")
        for f in found: self.cl_log.write(f"  · {f}", "warn")
        if found: self.cl_del_btn.config(state="normal")
        self.cl_pvar.set(100 if found else 0)

    def _cl_delete(self):
        if not self.cl_scan_results: return
        dry=self.cl_dry.get()
        mode="【模拟运行】" if dry else "【真实删除】"
        if self.cl_confirm.get():
            if not messagebox.askyesno("确认",
                f"{mode}\n即将操作 {len(self.cl_scan_results)} 个文件\n{'(模拟不实际删除)' if dry else '⚠ 不可撤销！'}\n确认继续？"):
                return
        files=list(self.cl_scan_results)
        def worker():
            ok=fail=0
            for i,fpath in enumerate(files):
                try:
                    if not dry: os.remove(fpath)
                    self.root.after(0, self.cl_log.write,
                        f"{'[模拟]' if dry else '[删除]'} {fpath}",
                        "dim" if dry else "err"); ok+=1
                except Exception as e:
                    self.root.after(0, self.cl_log.write, f"[失败] {fpath}  ← {e}", "warn"); fail+=1
                self.root.after(0, self.cl_pvar.set, (i+1)/len(files)*100)
            self.root.after(0, self.cl_log.write,
                f"{'模拟' if dry else '删除'}完成：成功 {ok} / 失败 {fail}", "ok")
            if not dry:
                self.cl_scan_results.clear()
                self.root.after(0, self.cl_del_btn.config, {"state":"disabled"})
        threading.Thread(target=worker, daemon=True).start()


    # ══════════════════════════════════════════════════
    #  Tab 4 — Obsidian 图片整理
    # ══════════════════════════════════════════════════
    _MD_IMG_RE = re.compile(r'!\[.*?\]\(([^)]+)\)')
    _OBS_IMG_EXTS = {".png",".jpg",".jpeg",".gif",".webp",".svg",".bmp"}

    def _build_tab_obsidian(self, parent):
        import urllib.parse as _ul; self._ul=_ul
        parent.columnconfigure(0, weight=1); parent.rowconfigure(1, weight=1)

        c = card(parent, padx=s(14), pady=s(12))
        c.grid(row=0, column=0, sticky="ew", padx=s(8), pady=(s(8),s(4)))
        c.columnconfigure(1, weight=1)

        self.obs_dir = tk.StringVar()
        entry_row(c, "Vault 根目录", self.obs_dir, 0, browse_dir=True)

        opt = tk.Frame(c, bg=PANEL); opt.grid(row=1, column=0, columnspan=3, sticky="w", pady=(s(8),s(4)))
        self.obs_dry       = tk.BooleanVar(value=True)
        self.obs_copy      = tk.BooleanVar(value=True)
        self.obs_recursive = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="预览模式（不实际移动）", variable=self.obs_dry).pack(side="left",padx=(0,s(12)))
        ttk.Checkbutton(opt, text="共享图片复制而非移动",  variable=self.obs_copy).pack(side="left",padx=(0,s(12)))
        ttk.Checkbutton(opt, text="递归处理所有子文件夹",  variable=self.obs_recursive).pack(side="left")

        br = tk.Frame(c, bg=PANEL); br.grid(row=2, column=0, columnspan=3, sticky="w", pady=(s(8),0))
        HBtn(br, text="▶  开始整理", bg=ACCENT, hbg=ACCENT2, fg="white",
             font=UIB, padx=s(14), pady=s(6), command=self._obs_run).pack(side="left",padx=(0,s(8)))
        HBtn(br, text="清空日志", bg=BORDER, hbg=BG3, fg=TEXT2, font=UIS,
             padx=s(10), pady=s(6), command=lambda: self.obs_log.clear()).pack(side="left")

        tk.Label(c, text="整理逻辑：将 MD 文件内引用的图片统一移至 image/<笔记名>/ 子目录，并同步更新引用路径",
                 bg=PANEL, fg=TEXT2, font=("Segoe UI",sf(8))).grid(
                     row=3, column=0, columnspan=3, sticky="w", pady=(s(8),0))

        self.obs_log = LogBox(parent, height=14)
        self.obs_log.grid(row=1, column=0, sticky="nsew", padx=s(8), pady=(0,s(8)))
        self.obs_log.write("填写 Vault 路径后点击「开始整理」，建议先保持预览模式", "dim")

    def _obs_run(self):
        d=self.obs_dir.get().strip()
        if not d or not Path(d).is_dir(): messagebox.showwarning("提示","请选择有效的 Vault 目录"); return
        dry=self.obs_dry.get(); copy=self.obs_copy.get(); recur=self.obs_recursive.get()
        self.obs_log.write(f"Vault: {d}", "info")
        self.obs_log.write(f"模式: {'预览' if dry else '执行'}  共享图片:{'复制' if copy else '移动'}  递归:{'是' if recur else '否'}", "info")
        def worker():
            vault=Path(d)
            pattern=vault.rglob("*.md") if recur else vault.glob("*.md")
            moved={}; total_moved=total_skip=0
            for md_file in sorted(pattern):
                try: content=md_file.read_text(encoding="utf-8")
                except: self.root.after(0,self.obs_log.write,f"读取失败:{md_file}","err"); continue
                note_name=md_file.stem; note_dir=md_file.parent
                refs=self._MD_IMG_RE.findall(content)
                if not refs: continue
                new_content=content; changed=False
                for ref in refs:
                    decoded=self._ul.unquote(ref); rp=Path(decoded)
                    parts=rp.parts
                    if rp.suffix.lower() not in self._OBS_IMG_EXTS: continue
                    if len(parts)==1: img_name=rp.name; src=note_dir/"image"/img_name
                    elif len(parts)==2 and parts[0]=="image": img_name=rp.name; src=note_dir/"image"/img_name
                    else: continue
                    if not src.exists(): continue
                    dst=note_dir/"image"/note_name/img_name
                    if src.resolve()==dst.resolve(): total_skip+=1; continue
                    new_ref="image/{}/{}".format(note_name.replace(" ","%20"),img_name.replace(" ","%20"))
                    sk=str(src.resolve())
                    if sk in moved and copy:
                        self.root.after(0,self.obs_log.write,f"[复制·共享] {md_file.name} {ref} → {new_ref}","info")
                        if not dry:
                            dst.parent.mkdir(parents=True,exist_ok=True)
                            shutil.copy2(str(moved[sk]),str(dst))
                    else:
                        self.root.after(0,self.obs_log.write,f"[移动] {md_file.name} {ref} → {new_ref}","warn")
                        if not dry:
                            dst.parent.mkdir(parents=True,exist_ok=True)
                            shutil.move(str(src),str(dst)); moved[sk]=dst
                    new_content=re.sub(r'(!\[.*?\]\()'+re.escape(ref)+r'(\))',
                                        r'\g<1>'+new_ref+r'\2', new_content)
                    changed=True; total_moved+=1
                if changed:
                    if not dry: md_file.write_text(new_content,encoding="utf-8")
                    self.root.after(0,self.obs_log.write,f"  ✓ {md_file.name} 引用已更新","ok")
            mode="（预览）" if dry else "（已执行）"
            self.root.after(0,self.obs_log.write,f"\n完成{mode} 移动/更新:{total_moved}  跳过:{total_skip}","ok")
            if dry: self.root.after(0,self.obs_log.write,"ℹ 预览完成。取消勾选「预览模式」后再次运行以实际执行","warn")
        threading.Thread(target=worker, daemon=True).start()


    # ══════════════════════════════════════════════════
    #  Tab 5 — 目录结构复制
    # ══════════════════════════════════════════════════
    def _build_tab_copy_struct(self, parent):
        parent.columnconfigure(0, weight=1); parent.rowconfigure(1, weight=1)

        c = card(parent, padx=s(14), pady=s(12))
        c.grid(row=0, column=0, sticky="ew", padx=s(8), pady=(s(8),s(4)))
        c.columnconfigure(1, weight=1)

        self.cs_src = tk.StringVar(); self.cs_dst = tk.StringVar()
        entry_row(c, "源目录", self.cs_src, 0, browse_dir=True)
        entry_row(c, "目标目录", self.cs_dst, 1, browse_dir=True)

        tk.Label(c, text="复制逻辑：递归复制目录树，每个子文件夹仅复制第一张图片（按文件名排序）",
                 bg=PANEL, fg=TEXT2, font=("Segoe UI",sf(8))).grid(
                     row=2, column=0, columnspan=3, sticky="w", pady=(s(4),s(8)))

        br = tk.Frame(c, bg=PANEL); br.grid(row=3, column=0, columnspan=3, sticky="w")
        HBtn(br, text="▶  开始复制", bg=ACCENT, hbg=ACCENT2, fg="white",
             font=UIB, padx=s(14), pady=s(6), command=self._cs_start).pack(side="left",padx=(0,s(8)))
        HBtn(br, text="清空日志", bg=BORDER, hbg=BG3, fg=TEXT2, font=UIS,
             padx=s(10), pady=s(6), command=lambda: self.cs_log.clear()).pack(side="left")

        self.cs_pvar = tk.DoubleVar()
        ttk.Progressbar(parent, variable=self.cs_pvar, maximum=100,
                         style="Bar.Horizontal.TProgressbar"
                         ).grid(row=1, column=0, sticky="ew", padx=s(8), pady=(0,s(4)))
        self.cs_log = LogBox(parent, height=14)
        self.cs_log.grid(row=2, column=0, sticky="nsew", padx=s(8), pady=(0,s(8)))
        parent.rowconfigure(2, weight=1)

    def _cs_start(self):
        src_s=self.cs_src.get().strip(); dst_s=self.cs_dst.get().strip()
        if not src_s or not dst_s: messagebox.showwarning("提示","请填写源目录和目标目录"); return
        src=Path(src_s); dst=Path(dst_s)
        if not src.is_dir(): messagebox.showerror("错误",f"源目录不存在：{src}"); return
        if dst.exists() and any(dst.iterdir()):
            if not messagebox.askyesno("目标非空","目标目录已有文件，同名文件将被覆盖，是否继续？"): return
        self.cs_pvar.set(0)
        self.cs_log.write(f"源目录: {src}", "info")
        self.cs_log.write(f"目标目录: {dst}", "info")
        def worker():
            all_dirs=[(r,ds_,fs) for r,ds_,fs in os.walk(src)]
            total=len(all_dirs); stats={"folders":0,"images":0,"skipped":0}
            for idx,(root,_,__) in enumerate(all_dirs):
                root_path=Path(root)
                rel=root_path.relative_to(src)
                target_dir=dst/rel
                target_dir.mkdir(parents=True,exist_ok=True)
                stats["folders"]+=1
                label=str(rel) if str(rel)!="." else "（根目录）"
                imgs=sorted([f for f in root_path.iterdir()
                              if f.is_file() and f.suffix.lower() in IMG_EXTS], key=lambda p:p.name)
                first=imgs[0] if imgs else None
                if first:
                    shutil.copy2(first, target_dir/first.name)
                    stats["images"]+=1
                    self.root.after(0, self.cs_log.write, f"✔  {label}  →  {first.name}", "ok")
                else:
                    stats["skipped"]+=1
                    self.root.after(0, self.cs_log.write, f"—  {label}  （无图片）", "dim")
                self.root.after(0, self.cs_pvar.set, (idx+1)/total*100)
            self.root.after(0, self.cs_log.write,
                f"完成！创建文件夹 {stats['folders']} 个  复制图片 {stats['images']} 张  空文件夹 {stats['skipped']} 个",
                "ok")
        threading.Thread(target=worker, daemon=True).start()


    # ══════════════════════════════════════════════════
    #  Tab 6 — WebP 转视频
    # ══════════════════════════════════════════════════
    def _build_tab_webp(self, parent):
        parent.columnconfigure(0, weight=1); parent.rowconfigure(2, weight=1)

        c = card(parent, padx=s(14), pady=s(12))
        c.grid(row=0, column=0, sticky="ew", padx=s(8), pady=(s(8),s(4)))
        c.columnconfigure(1, weight=1)

        self.wp_src = tk.StringVar(); self.wp_out = tk.StringVar()
        def _pick_src():
            d=filedialog.askdirectory(title="选择包含 WebP 文件的文件夹")
            if d:
                self.wp_src.set(d)
                if not self.wp_out.get(): self.wp_out.set(str(Path(d)/"output.mp4"))
                self._wp_refresh()
        tk.Label(c, text="输入文件夹", bg=PANEL, fg=TEXT2, font=UIS, width=16, anchor="w"
                 ).grid(row=0, column=0, sticky="w", padx=(0,s(8)), pady=s(5))
        ef0 = tk.Frame(c, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        ef0.grid(row=0, column=1, sticky="ew", pady=s(5))
        tk.Entry(ef0, textvariable=self.wp_src, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=UI, bd=6).pack(fill="x")
        HBtn(c, text="浏览", bg=BORDER, hbg=ACCENT2, fg=TEXT, font=UIS,
             padx=s(10), pady=s(5), command=_pick_src).grid(row=0, column=2, padx=(s(8),0), pady=s(5))

        entry_row(c, "输出文件", self.wp_out, 1, browse_save=True,
                  filetypes=[("MP4","*.mp4"),("MOV","*.mov"),("AVI","*.avi")])

        # 编解码器
        tk.Label(c, text="编码格式", bg=PANEL, fg=TEXT2, font=UIS, width=16, anchor="w"
                 ).grid(row=2, column=0, sticky="w", padx=(0,s(8)), pady=s(5))
        self.wp_codec_label = tk.StringVar(value="libx264 (MP4, 最兼容)")
        self._wp_codec_map = {"libx264 (MP4, 最兼容)":"libx264",
                              "libx265 (MP4, 更小体积)":"libx265",
                              "mjpeg (AVI, 高画质)":"mjpeg"}
        cb = ttk.Combobox(c, textvariable=self.wp_codec_label,
                          values=list(self._wp_codec_map.keys()),
                          state="readonly", width=28)
        cb.grid(row=2, column=1, sticky="w", pady=s(5))

        # 质量滑块
        tk.Label(c, text="质量 CRF", bg=PANEL, fg=TEXT2, font=UIS, width=16, anchor="w"
                 ).grid(row=3, column=0, sticky="w", padx=(0,s(8)), pady=s(5))
        self.wp_crf = tk.IntVar(value=18)
        crf_row = tk.Frame(c, bg=PANEL); crf_row.grid(row=3, column=1, columnspan=2, sticky="w")
        self.wp_crf_lbl = tk.Label(crf_row, text="18  (0=最佳, 51=最差)", bg=PANEL, fg=TEXT2, font=UIS)
        sc = ttk.Scale(crf_row, from_=0, to=51, variable=self.wp_crf, orient="horizontal", length=s(200),
                       command=lambda v: self.wp_crf_lbl.config(text=f"{int(float(v))}  (0=最佳, 51=最差)"))
        sc.pack(side="left", padx=(0,s(8))); self.wp_crf_lbl.pack(side="left")

        br = tk.Frame(c, bg=PANEL); br.grid(row=4, column=0, columnspan=3, sticky="w", pady=(s(10),0))
        HBtn(br, text="🔄 刷新列表", bg=BORDER, hbg=BG3, fg=TEXT, font=UIS,
             padx=s(10), pady=s(6), command=self._wp_refresh).pack(side="left",padx=(0,s(8)))
        HBtn(br, text="▶  开始转换", bg=ACCENT, hbg=ACCENT2, fg="white",
             font=UIB, padx=s(14), pady=s(6), command=self._wp_start).pack(side="left")

        # 文件列表
        lf = card(parent, padx=s(4), pady=s(4))
        lf.grid(row=1, column=0, sticky="ew", padx=s(8), pady=(0,s(4)))
        lf.columnconfigure(0, weight=1)
        tk.Label(lf, text="将处理的文件（按文件名排序）",
                 bg=PANEL, fg=TEXT2, font=UIS).pack(anchor="w", padx=s(4), pady=(s(4),s(2)))
        lb_f = tk.Frame(lf, bg=BORDER, padx=1, pady=1); lb_f.pack(fill="x")
        lb_f.columnconfigure(0, weight=1)
        self.wp_lb = tk.Listbox(lb_f, bg=BG3, fg=TEXT, font=MONO, height=5,
                                 bd=0, highlightthickness=0, relief="flat")
        self.wp_lb.grid(row=0, column=0, sticky="ew")
        vsb4 = ttk.Scrollbar(lb_f, orient="vertical", command=self.wp_lb.yview)
        vsb4.grid(row=0, column=1, sticky="ns")
        self.wp_lb.configure(yscrollcommand=vsb4.set)

        self.wp_pvar = tk.DoubleVar()
        ttk.Progressbar(parent, variable=self.wp_pvar, maximum=100,
                         style="Bar.Horizontal.TProgressbar"
                         ).grid(row=2, column=0, sticky="ew", padx=s(8), pady=(0,s(4)))
        self.wp_log = LogBox(parent, height=6)
        self.wp_log.grid(row=3, column=0, sticky="nsew", padx=s(8), pady=(0,s(8)))
        parent.rowconfigure(3, weight=1)

    def _wp_refresh(self):
        src=self.wp_src.get().strip()
        self.wp_lb.delete(0,"end")
        if not src or not os.path.isdir(src): return
        files=sorted([f.name for f in Path(src).iterdir() if f.suffix.lower()==".webp"])
        for f in files: self.wp_lb.insert("end",f)
        self.wp_log.write(f"找到 {len(files)} 个 .webp 文件")

    def _wp_start(self):
        src=self.wp_src.get().strip(); out=self.wp_out.get().strip()
        if not src or not os.path.isdir(src): messagebox.showerror("错误","请选择有效输入文件夹"); return
        if not out: messagebox.showerror("错误","请指定输出文件路径"); return
        if not PIL_OK: messagebox.showerror("缺少依赖","请先安装：pip install pillow"); return
        if not shutil.which("ffmpeg"):
            messagebox.showerror("缺少 ffmpeg",
                "未找到 ffmpeg！\nmacOS: brew install ffmpeg\n"
                "Ubuntu: sudo apt install ffmpeg\nWindows: https://ffmpeg.org"); return
        files=sorted([str(f) for f in Path(src).iterdir() if f.suffix.lower()==".webp"])
        if not files: messagebox.showerror("错误","没有找到 .webp 文件"); return
        codec=self._wp_codec_map[self.wp_codec_label.get()]; crf=self.wp_crf.get()
        self.wp_pvar.set(0)
        def worker():
            try: self._wp_convert(files, out, codec, crf)
            except Exception as e:
                self.root.after(0, self.wp_log.write, f"错误: {e}", "err")
        threading.Thread(target=worker, daemon=True).start()

    def _wp_convert(self, webp_files, output_path, codec, crf):
        total=len(webp_files)
        self.root.after(0, self.wp_log.write, f"共 {total} 个文件，开始解析...", "info")
        all_frames=[]
        for i,path in enumerate(webp_files):
            try:
                frames=self._wp_parse_frames(path)
                all_frames.extend(frames)
                self.root.after(0, self.wp_log.write, f"[{i+1}/{total}] {Path(path).name}  ({len(frames)} 帧)")
            except Exception as e:
                self.root.after(0, self.wp_log.write, f"跳过 {Path(path).name}: {e}", "warn")
            self.root.after(0, self.wp_pvar.set, (i+1)/(total*2)*100)
        if not all_frames: raise RuntimeError("没有解析到任何帧")
        max_w=max(f[0].width for f in all_frames); max_h=max(f[0].height for f in all_frames)
        max_w+=max_w%2; max_h+=max_h%2
        self.root.after(0, self.wp_log.write, f"分辨率: {max_w}x{max_h}，共 {len(all_frames)} 帧", "info")
        tmpdir=tempfile.mkdtemp(prefix="webp2vid_")
        concat_file=os.path.join(tmpdir,"concat.txt")
        try:
            with open(concat_file,"w",encoding="utf-8") as cf:
                for j,(img,dur_ms) in enumerate(all_frames):
                    bg=Image.new("RGB",img.size,(0,0,0))
                    bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
                    if bg.width!=max_w or bg.height!=max_h:
                        nb=Image.new("RGB",(max_w,max_h),(0,0,0)); nb.paste(bg,(0,0)); bg=nb
                    fp=os.path.join(tmpdir,f"frame_{j:06d}.png"); bg.save(fp,"PNG")
                    cf.write(f"file '{fp}'\nduration {dur_ms/1000:.6f}\n")
                    self.root.after(0, self.wp_pvar.set, 50+(j+1)/len(all_frames)*50)
            ext=Path(output_path).suffix.lower()
            if ext==".avi": extra=["-c:v",codec]
            elif ext==".mov": extra=["-c:v",codec,"-movflags","+faststart"]
            else: extra=["-c:v",codec,"-crf",str(crf),"-preset","medium","-movflags","+faststart","-pix_fmt","yuv420p"]
            cmd=["ffmpeg","-y","-f","concat","-safe","0","-i",concat_file,*extra,output_path]
            self.root.after(0, self.wp_log.write, "调用 ffmpeg 编码...", "info")
            result=subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode!=0: raise RuntimeError(f"ffmpeg 错误:\n{result.stderr[-1000:]}")
            self.root.after(0, self.wp_log.write, f"✅ 完成！输出: {output_path}", "ok")
            self.root.after(0, self.wp_pvar.set, 100)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _wp_parse_frames(self, path):
        with open(path,"rb") as f: data=f.read()
        img=Image.open(path)
        if not hasattr(img,"n_frames") or img.n_frames==1:
            img.seek(0); return [(img.convert("RGBA"),100)]
        durations=[]
        for m in re.finditer(b"ANMF",data):
            pos=m.start()+8
            dur=struct.unpack_from("<I",data,pos+12)[0]&0xFFFFFF
            durations.append(max(dur,1))
        frames=[]
        for i in range(img.n_frames):
            img.seek(i); frame=img.copy().convert("RGBA")
            dur=durations[i] if i<len(durations) else 100
            frames.append((frame,dur))
        return frames


# ══════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
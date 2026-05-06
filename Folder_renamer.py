import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re, threading, time
from pathlib import Path

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0f0f12"
PANEL   = "#17171d"
BORDER  = "#2a2a35"
ACCENT  = "#6c63ff"
ACCENT2 = "#a78bfa"
SUCCESS = "#34d399"
WARNING = "#fbbf24"
DANGER  = "#f87171"
TEXT    = "#e8e8f0"
SUB     = "#9090a8"
ENTRY   = "#1e1e28"
BHOV    = "#5a52e8"
MONO    = ("Consolas", 9)
UI      = ("Segoe UI", 10)
UIS     = ("Segoe UI", 9)
UIB     = ("Segoe UI", 10, "bold")
H1      = ("Segoe UI", 14, "bold")
H2      = ("Segoe UI", 10, "bold")


def card(parent, **kw):
    """Bordered panel."""
    return tk.Frame(parent, bg=PANEL,
                    highlightbackground=BORDER, highlightthickness=1, **kw)


class HBtn(tk.Button):
    def __init__(self, master, hbg=BHOV, **kw):
        self._n = kw.get("bg", ACCENT)
        self._h = hbg
        super().__init__(master, relief="flat", bd=0, cursor="hand2", **kw)
        self.bind("<Enter>", lambda e: self.config(bg=self._h))
        self.bind("<Leave>", lambda e: self.config(bg=self._n))


class App:
    _PRE = re.compile(r"^\d+-")

    def __init__(self, root):
        self.root = root
        root.title("文件夹批量重命名")
        root.configure(bg=BG)
        root.minsize(680, 500)
        root.geometry("940x660")

        self.folders = []
        self.running = False
        self._stop   = False

        self._styles()

        # ── pack order: bottom-bar FIRST so it's never squeezed off ──────
        self._mk_header()
        self._mk_bottombar()   # <-- packed with side="bottom" BEFORE body
        self._mk_body()

        self._on_mode()        # init toggle visuals

    # ── ttk styles ────────────────────────────────────────────────────────────
    def _styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Bar.Horizontal.TProgressbar",
                    background=ACCENT, troughcolor=BORDER,
                    borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT)
        for n, bg in (("Pnl.TCheckbutton", PANEL), ("Bg.TCheckbutton", BG)):
            s.configure(n, background=bg, foreground=TEXT,
                        font=UI, focuscolor=ACCENT)
            s.map(n, background=[("active", bg)],
                     foreground=[("active", ACCENT2)])

    # ── Header ────────────────────────────────────────────────────────────────
    def _mk_header(self):
        f = tk.Frame(self.root, bg=BG, pady=8)
        f.pack(fill="x", padx=16)
        tk.Label(f, text="📁", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 18)).pack(side="left", padx=(0, 6))
        tk.Label(f, text="文件夹批量重命名", bg=BG, fg=TEXT,
                 font=H1).pack(side="left")
        self._sub = tk.Label(f, text="", bg=BG, fg=SUB, font=UIS)
        self._sub.pack(side="left", padx=10, pady=(2, 0))
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=16)

    # ── Bottom action bar ─────────────────────────────────────────────────────
    def _mk_bottombar(self):
        tk.Frame(self.root, bg=BORDER, height=1).pack(
            fill="x", padx=16, side="bottom")
        bar = tk.Frame(self.root, bg=PANEL, padx=16, pady=9)
        bar.pack(fill="x", side="bottom")   # anchored at bottom

        self._status = tk.Label(bar,
            text="✦  准备就绪，请添加文件夹并配置参数",
            bg=PANEL, fg=SUB, font=UIS)
        self._status.pack(side="left")

        self._stop_btn = HBtn(bar, text="⏹  停止",
            bg=PANEL, hbg="#2a1a1a", fg=DANGER, font=UI,
            padx=12, pady=6, state="disabled",
            command=self._stop_rename)
        self._stop_btn.pack(side="right", padx=(6, 0))

        self._run_btn = HBtn(bar, text="▶  开始重命名",
            bg=ACCENT, hbg=BHOV, fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=18, pady=6, command=self._start)
        self._run_btn.pack(side="right")

    # ── Body: left list | right panels ───────────────────────────────────────
    def _mk_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=10)

        # Two columns: list(weight 3) + controls(weight 2)
        body.columnconfigure(0, weight=3, minsize=220)
        body.columnconfigure(1, weight=2, minsize=260)
        body.rowconfigure(0, weight=1)

        self._mk_list(body)
        self._mk_right(body)

    # ── Left: folder list ─────────────────────────────────────────────────────
    def _mk_list(self, body):
        lf = tk.Frame(body, bg=BG)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(1, weight=1)

        # title row
        th = tk.Frame(lf, bg=BG)
        th.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        tk.Label(th, text="待处理文件夹", bg=BG, fg=TEXT,
                 font=H2).pack(side="left")
        self._cnt = tk.Label(th, text="( 0 个 )",
                              bg=BG, fg=SUB, font=UIS)
        self._cnt.pack(side="left", padx=5)

        # listbox
        lbf = tk.Frame(lf, bg=BORDER, padx=1, pady=1)
        lbf.grid(row=1, column=0, sticky="nsew")
        lbf.rowconfigure(0, weight=1)
        lbf.columnconfigure(0, weight=1)

        self.lb = tk.Listbox(lbf, bg=PANEL, fg=TEXT,
                              selectbackground=ACCENT, selectforeground="#fff",
                              font=MONO, bd=0, highlightthickness=0,
                              activestyle="none", relief="flat")
        self.lb.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(lbf, orient="vertical", command=self.lb.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(lbf, orient="horizontal", command=self.lb.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.lb.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # buttons below list
        bb = tk.Frame(lf, bg=BG)
        bb.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        for txt, bg, hbg, fg, cmd in [
            ("＋ 选择文件夹", ACCENT,    BHOV,      "white",  self._add_single),
            ("📂 导入子目录", "#1e3a1e", "#1a501a",  SUCCESS,  self._add_parent),
            ("✕ 移除选中",   "#2e1e1e", "#3d2020",  DANGER,   self._remove),
            ("清空",          PANEL,     BORDER,    SUB,      self._clear),
        ]:
            HBtn(bb, text=txt, bg=bg, hbg=hbg, fg=fg,
                 font=UIS, padx=9, pady=5,
                 command=cmd).pack(side="left", padx=(0, 3))

    # ── Right: 3 rows (settings / progress / log) all resizable ──────────────
    def _mk_right(self, body):
        rf = tk.Frame(body, bg=BG)
        rf.grid(row=0, column=1, sticky="nsew")
        rf.columnconfigure(0, weight=1)
        # row weights: settings fixed-ish, progress fixed, log expands
        rf.rowconfigure(0, weight=0)  # settings
        rf.rowconfigure(1, weight=0)  # progress
        rf.rowconfigure(2, weight=1)  # log expands

        self._mk_settings(rf)
        self._mk_progress(rf)
        self._mk_log(rf)

    # ── Settings card ─────────────────────────────────────────────────────────
    def _mk_settings(self, parent):
        c = card(parent, padx=14, pady=12)
        c.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        c.columnconfigure(0, weight=1)

        # — mode toggle —
        tk.Label(c, text="删除模式", bg=PANEL, fg=SUB, font=UIS).pack(
            anchor="w", pady=(0, 4))

        self._mode = tk.StringVar(value="fixed")
        mr = tk.Frame(c, bg=PANEL)
        mr.pack(fill="x", pady=(0, 8))
        mr.columnconfigure(0, weight=1)
        mr.columnconfigure(1, weight=1)

        self._mb_fix = tk.Button(mr, text="固定字符数", font=UIS,
            bg=BORDER, fg=SUB, relief="flat", bd=0, pady=7, cursor="hand2",
            command=lambda: self._mode.set("fixed"))
        self._mb_fix.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self._mb_pre = tk.Button(mr, text="数字前缀＋连字符", font=UIS,
            bg=BORDER, fg=SUB, relief="flat", bd=0, pady=7, cursor="hand2",
            command=lambda: self._mode.set("prefix"))
        self._mb_pre.grid(row=0, column=1, sticky="ew")

        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        # — fixed-N panel —
        self._fix_f = tk.Frame(c, bg=PANEL)
        row = tk.Frame(self._fix_f, bg=PANEL)
        row.pack(anchor="w")
        tk.Label(row, text="删除前", bg=PANEL, fg=TEXT, font=UI).pack(side="left")
        self._nvar = tk.IntVar(value=2)
        HBtn(row, text="−", bg=BORDER, hbg=ACCENT, fg="white",
             font=("Segoe UI", 11, "bold"), width=2,
             command=lambda: self._adjn(-1)).pack(side="left", padx=(8, 2))
        tk.Entry(row, textvariable=self._nvar, bg=ENTRY, fg=TEXT,
                 font=("Consolas", 12, "bold"), width=4, justify="center",
                 bd=0, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT, insertbackground=TEXT).pack(
            side="left", padx=2)
        HBtn(row, text="＋", bg=BORDER, hbg=ACCENT, fg="white",
             font=("Segoe UI", 11, "bold"), width=2,
             command=lambda: self._adjn(1)).pack(side="left", padx=(2, 8))
        tk.Label(row, text="个字符", bg=PANEL, fg=TEXT, font=UI).pack(side="left")
        self._nvar.trace_add("write", lambda *a: self._preview())

        # — prefix panel —
        self._pre_f = tk.Frame(c, bg=PANEL)
        ib = tk.Frame(self._pre_f, bg=ENTRY,
                      highlightbackground=BORDER, highlightthickness=1)
        ib.pack(fill="x", pady=(0, 6))
        tk.Label(ib, text="匹配规则：^\\d+-  （数字串 + 连字符「-」）",
                 bg=ENTRY, fg=ACCENT2, font=("Consolas", 9)).pack(
            anchor="w", padx=8, pady=5)
        eg = tk.Frame(ib, bg=ENTRY)
        eg.pack(anchor="w", padx=8, pady=(0, 5))
        for o, r in [("01-项目文档","项目文档"),
                     ("123-设计稿","设计稿"),
                     ("9999-归档","归档")]:
            rr = tk.Frame(eg, bg=ENTRY)
            rr.pack(anchor="w")
            tk.Label(rr, text=f"{o}  →  ", bg=ENTRY,
                     fg=SUB, font=("Consolas", 8)).pack(side="left")
            tk.Label(rr, text=r, bg=ENTRY,
                     fg=SUCCESS, font=("Consolas", 8)).pack(side="left")
        nm = tk.Frame(self._pre_f, bg=PANEL)
        nm.pack(fill="x")
        tk.Label(nm, text="未匹配时：", bg=PANEL, fg=TEXT,
                 font=UI).pack(side="left")
        self._nm = tk.StringVar(value="skip")
        for v, l in [("skip","跳过"), ("keep","保留原名")]:
            tk.Radiobutton(nm, text=l, variable=self._nm, value=v,
                           bg=PANEL, fg=TEXT, selectcolor=ENTRY,
                           activebackground=PANEL, font=UIS,
                           cursor="hand2").pack(side="left", padx=(6, 0))
        self._nm.trace_add("write", lambda *a: self._preview())

        # — options row —
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=8)
        opt = tk.Frame(c, bg=PANEL)
        opt.pack(fill="x", pady=(0, 6))
        self._skip_hid = tk.BooleanVar(value=True)
        self._dry      = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="跳过隐藏文件夹",
                        variable=self._skip_hid,
                        style="Pnl.TCheckbutton").pack(side="left", padx=(0,14))
        ttk.Checkbutton(opt, text="试运行（不实际重命名）",
                        variable=self._dry,
                        style="Pnl.TCheckbutton").pack(side="left")

        # — preview box —
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(0, 6))
        tk.Label(c, text="重命名预览", bg=PANEL, fg=SUB,
                 font=UIS).pack(anchor="w", pady=(0, 3))
        self._pvw = tk.Label(c,
            text="─ 请在左侧选中一个文件夹查看预览 ─",
            bg=ENTRY, fg=ACCENT2, font=("Consolas", 9),
            anchor="w", justify="left", padx=8, pady=6,
            highlightbackground=BORDER, highlightthickness=1)
        self._pvw.pack(fill="x")

        self.lb.bind("<<ListboxSelect>>", self._preview)
        self._mode.trace_add("write", lambda *a: self._on_mode())

    # ── Progress card ─────────────────────────────────────────────────────────
    def _mk_progress(self, parent):
        c = card(parent, padx=14, pady=10)
        c.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        hr = tk.Frame(c, bg=PANEL)
        hr.pack(fill="x", pady=(0, 6))
        tk.Label(hr, text="执行进度", bg=PANEL, fg=TEXT,
                 font=H2).pack(side="left")
        self._plbl = tk.Label(hr, text="就绪", bg=PANEL, fg=SUB, font=UIS)
        self._plbl.pack(side="right")

        self._pvar = tk.DoubleVar(value=0)
        ttk.Progressbar(c, variable=self._pvar, maximum=100,
                         style="Bar.Horizontal.TProgressbar").pack(
            fill="x", pady=(0, 6))

        sr = tk.Frame(c, bg=PANEL)
        sr.pack(fill="x")
        sr.columnconfigure(0, weight=1)
        sr.columnconfigure(1, weight=1)
        sr.columnconfigure(2, weight=1)
        self._s_done = self._statbox(sr, "完成", SUCCESS, 0)
        self._s_skip = self._statbox(sr, "跳过", WARNING, 1)
        self._s_fail = self._statbox(sr, "失败", DANGER,  2)

    def _statbox(self, parent, lbl, color, col):
        f = tk.Frame(parent, bg=BORDER, padx=8, pady=5)
        f.grid(row=0, column=col, sticky="ew",
               padx=(0, 4) if col < 2 else 0)
        v = tk.Label(f, text="0", bg=BORDER, fg=color,
                     font=("Segoe UI", 15, "bold"))
        v.pack()
        tk.Label(f, text=lbl, bg=BORDER, fg=SUB, font=UIS).pack()
        return v

    # ── Log card (expands to fill remaining space) ────────────────────────────
    def _mk_log(self, parent):
        c = card(parent, padx=14, pady=10)
        c.grid(row=2, column=0, sticky="nsew")
        c.rowconfigure(1, weight=1)
        c.columnconfigure(0, weight=1)

        hr = tk.Frame(c, bg=PANEL)
        hr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        tk.Label(hr, text="执行日志", bg=PANEL, fg=TEXT, font=H2).pack(side="left")
        HBtn(hr, text="清除", bg=PANEL, hbg=BORDER, fg=SUB, font=UIS,
             padx=7, pady=2,
             command=lambda: self._log_box.delete("1.0", "end")).pack(
            side="right")

        self._log_box = tk.Text(c, bg=ENTRY, fg=TEXT, font=MONO,
                                 bd=0, relief="flat", state="disabled",
                                 highlightthickness=0, wrap="none")
        self._log_box.grid(row=1, column=0, sticky="nsew")
        lv = ttk.Scrollbar(c, orient="vertical",
                            command=self._log_box.yview)
        lv.grid(row=1, column=1, sticky="ns")
        self._log_box.configure(yscrollcommand=lv.set)
        for tag, col in [("ok", SUCCESS), ("skip", WARNING),
                          ("err", DANGER),  ("info", ACCENT2)]:
            self._log_box.tag_config(tag, foreground=col)

    # ── Mode toggle ───────────────────────────────────────────────────────────
    def _on_mode(self):
        if self._mode.get() == "fixed":
            self._mb_fix.config(bg=ACCENT, fg="white")
            self._mb_pre.config(bg=BORDER, fg=SUB)
            self._pre_f.pack_forget()
            self._fix_f.pack(fill="x")
            self._sub.config(text="— 删除前 N 个字符")
        else:
            self._mb_pre.config(bg=ACCENT, fg="white")
            self._mb_fix.config(bg=BORDER, fg=SUB)
            self._fix_f.pack_forget()
            self._pre_f.pack(fill="x")
            self._sub.config(text="— 自动删除「数字串-」前缀")
        self._preview()

    # ── Folder management ─────────────────────────────────────────────────────
    def _add_single(self):
        added = []
        while True:
            d = filedialog.askdirectory(title="选择文件夹", mustexist=True)
            if not d: break
            p = Path(d)
            if p not in self.folders:
                added.append(p)
            if not messagebox.askyesno("继续", "是否继续添加更多文件夹？"):
                break
        self._bulk_add(added)

    def _add_parent(self):
        d = filedialog.askdirectory(
            title="选择父文件夹（导入所有直接子文件夹）", mustexist=True)
        if not d: return
        p = Path(d)
        ch = [c for c in p.iterdir() if c.is_dir()]
        if not ch:
            messagebox.showinfo("提示", "该文件夹下没有子文件夹")
            return
        self._bulk_add(ch)
        self._log(f"从 {p.name} 导入 {len(ch)} 个子文件夹", "info")

    def _bulk_add(self, paths):
        n = 0
        for p in paths:
            if p not in self.folders:
                self.folders.append(p)
                self.lb.insert("end", str(p))
                n += 1
        self._cnt.config(text=f"( {len(self.folders)} 个 )")
        if n: self._setstatus(f"✦  已添加 {n} 个，共 {len(self.folders)} 个")
        self._preview()

    def _remove(self):
        for i in reversed(self.lb.curselection()):
            self.lb.delete(i); del self.folders[i]
        self._cnt.config(text=f"( {len(self.folders)} 个 )")
        self._preview()

    def _clear(self):
        if self.folders and messagebox.askyesno("确认", "清空列表？"):
            self.folders.clear(); self.lb.delete(0, "end")
            self._cnt.config(text="( 0 个 )")
            self._preview()

    # ── Compute new name ──────────────────────────────────────────────────────
    def _new_name(self, name):
        if self._mode.get() == "fixed":
            try: n = self._nvar.get()
            except: n = 0
            return None if n <= 0 or n >= len(name) else name[n:]
        else:
            m = self._PRE.match(name)
            if not m:
                return name if self._nm.get() == "keep" else None
            return name[m.end():]

    # ── Preview ───────────────────────────────────────────────────────────────
    def _preview(self, _=None):
        sel = self.lb.curselection()
        name = (self.folders[sel[0]].name if sel
                else (self.folders[0].name if self.folders else None))
        if not name:
            self._pvw.config(text="─ 请在左侧选中一个文件夹查看预览 ─")
            return
        if self._mode.get() == "fixed":
            try: n = self._nvar.get()
            except: n = 0
            if 0 < n < len(name):
                self._pvw.config(
                    text=f"原名:  {name}\n删前:  {'─'*n}{name[n:]}\n新名:  {name[n:]}")
            else:
                self._pvw.config(
                    text=f"原名:  {name}\n状态:  名称过短或 N 无效")
        else:
            m = self._PRE.match(name)
            if m:
                self._pvw.config(
                    text=(f"原名:  {name}\n"
                          f"前缀:  「{name[:m.end()]}」\n"
                          f"新名:  {name[m.end():]}"))
            else:
                act = "保留原名" if self._nm.get() == "keep" else "跳过"
                self._pvw.config(
                    text=f"原名:  {name}\n匹配:  无数字-前缀\n操作:  {act}")

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def _start(self):
        if not self.folders:
            messagebox.showwarning("提示", "请先添加要处理的文件夹"); return
        if self._mode.get() == "fixed":
            try:
                n = self._nvar.get(); assert n > 0
            except:
                messagebox.showerror("错误", "请输入有效正整数"); return
            desc = f"删除前 {n} 个字符"
        else:
            desc = "自动删除「数字串-」前缀"

        if not self._dry.get():
            if not messagebox.askyesno("确认操作",
                    f"将对 {len(self.folders)} 个文件夹执行：{desc}\n"
                    "此操作不可撤销，是否继续？"):
                return

        self.running = True; self._stop = False
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._s_done.config(text="0"); self._s_skip.config(text="0")
        self._s_fail.config(text="0"); self._pvar.set(0)
        pfx = "【试运行】" if self._dry.get() else ""
        self._log(f"{pfx}开始 · {len(self.folders)} 个 · {desc}", "info")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        total = len(self.folders)
        done = skip = fail = 0
        dry = self._dry.get()
        renamed = {}

        for i, folder in enumerate(self.folders):
            if self._stop:
                self.root.after(0, self._log, "⏹ 用户终止", "info"); break

            pct = i / total * 100
            self.root.after(0, self._pvar.set, pct)
            self.root.after(0, self._plbl.config,
                            {"text": f"{i+1}/{total}  ({pct:.0f}%)"})

            name = folder.name; par = folder.parent

            if self._skip_hid.get() and name.startswith("."):
                skip += 1
                self.root.after(0, self._log, f"跳过隐藏: {name}", "skip")
                self.root.after(0, self._s_skip.config, {"text": str(skip)})
                self._hl(i, WARNING); continue

            nn = self._new_name(name)

            if nn is None:
                skip += 1
                r = "名称过短" if self._mode.get() == "fixed" else "无匹配前缀"
                self.root.after(0, self._log, f"跳过({r}): {name}", "skip")
                self.root.after(0, self._s_skip.config, {"text": str(skip)})
                self._hl(i, WARNING); continue

            if nn == name:
                skip += 1
                self.root.after(0, self._log, f"保留原名: {name}", "skip")
                self.root.after(0, self._s_skip.config, {"text": str(skip)})
                self._hl(i, WARNING); continue

            np = par / nn
            if np.exists():
                fail += 1
                self.root.after(0, self._log, f"冲突: {name} → {nn}", "err")
                self.root.after(0, self._s_fail.config, {"text": str(fail)})
                self._hl(i, DANGER); continue

            if dry:
                done += 1
                self.root.after(0, self._log, f"[试] {name} → {nn}", "ok")
                self.root.after(0, self._s_done.config, {"text": str(done)})
                self._hl(i, SUCCESS)
            else:
                try:
                    folder.rename(np); renamed[folder] = np; done += 1
                    self.root.after(0, self._log, f"✓ {name} → {nn}", "ok")
                    self.root.after(0, self._s_done.config, {"text": str(done)})
                    self._hl(i, SUCCESS)
                except Exception as e:
                    fail += 1
                    self.root.after(0, self._log, f"✗ {name}  {e}", "err")
                    self.root.after(0, self._s_fail.config, {"text": str(fail)})
                    self._hl(i, DANGER)

            time.sleep(0.001)

        self.root.after(0, self._pvar.set, 100)
        s = f"完成 {done} · 跳过 {skip} · 失败 {fail}"
        self.root.after(0, self._plbl.config, {"text": f"完毕  {s}"})
        self.root.after(0, self._log, "─"*34, "info")
        self.root.after(0, self._log, s, "info")
        self.root.after(0, self._setstatus, f"✦  {s}", SUCCESS)
        self.root.after(0, self._run_btn.config, {"state": "normal"})
        self.root.after(0, self._stop_btn.config, {"state": "disabled"})
        if not dry and renamed:
            self.root.after(200, self._refresh, renamed)
        self.running = False

    def _hl(self, i, c):
        self.root.after(0, lambda: self.lb.itemconfig(i, {"fg": c}))

    def _refresh(self, renamed):
        self.lb.delete(0, "end"); nf = []
        for p in self.folders:
            np = renamed.get(p, p)
            if not np.exists() and p.exists(): np = p
            nf.append(np); self.lb.insert("end", str(np))
        self.folders = nf

    def _stop_rename(self):
        self._stop = True
        self._setstatus("⏹  正在停止…", WARNING)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _adjn(self, d):
        try: self._nvar.set(max(1, self._nvar.get() + d))
        except: self._nvar.set(1)

    def _log(self, msg, tag="info"):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n", tag)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _setstatus(self, msg, color=SUB):
        self._status.config(text=msg, fg=color)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
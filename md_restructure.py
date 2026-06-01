import os
import re
import urllib.parse
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import tkinter.font as tkfont

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


def find_md_image_refs(content):
    return re.findall(r'!\[.*?\]\(([^)]+)\)', content)


def resolve_ref(ref, note_dir):
    """
    解析引用，返回 (src_path, img_name) 或 None。
    支持：
      1. image/xxx.png          — 已在 image/ 下，未按笔记分类
      2. Pasted%20image.png     — URL编码，图片实际在 image/ 下
      3. xxx.png                — 普通文件名，图片实际在 image/ 下
    跳过已分类好的 image/<笔记名>/xxx.png（parts==3）
    """
    decoded = urllib.parse.unquote(ref)
    ref_path = Path(decoded)
    parts = ref_path.parts

    if ref_path.suffix.lower() not in IMAGE_EXTS:
        return None

    if len(parts) == 1:
        # 无路径前缀：在 image/ 下找
        img_name = ref_path.name
        src = note_dir / "image" / img_name
        if src.exists():
            return src, img_name
        return None

    if len(parts) == 2 and parts[0] == "image":
        # image/xxx.png：已在 image/ 子目录，但未分类
        img_name = ref_path.name
        src = note_dir / "image" / img_name
        if src.exists():
            return src, img_name
        return None

    # 其他（已分类的 image/笔记名/xxx.png 等）跳过
    return None


def process_vault(vault_root, dry_run, copy_shared, recursive, log_callback, done_callback):
    vault = Path(vault_root)
    pattern = vault.rglob("*.md") if recursive else vault.glob("*.md")
    moved_files = {}
    total_moved = 0
    total_skipped = 0
    total_warn = 0

    for md_file in sorted(pattern):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            log_callback("warn", f"读取失败: {md_file}  ({e})\n")
            continue

        note_name = md_file.stem
        note_dir = md_file.parent
        refs = find_md_image_refs(content)
        if not refs:
            continue

        new_content = content
        changed = False

        for ref in refs:
            result = resolve_ref(ref, note_dir)
            if result is None:
                continue

            src, img_name = result
            dst = note_dir / "image" / note_name / img_name

            if src.resolve() == dst.resolve():
                total_skipped += 1
                continue

            # 空格编码为 %20，其他字符保持原样
            # Obsidian 需要 %20 表示空格才能正确解析相对路径
            new_ref = "image/{}/{}".format(
                note_name.replace(" ", "%20"),
                img_name.replace(" ", "%20")
            )
            src_key = str(src.resolve())

            if src_key in moved_files and copy_shared:
                log_callback("copy", f"[复制·共享] {md_file.name}\n  {ref}  →  {new_ref}\n")
                if not dry_run:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(moved_files[src_key]), str(dst))
            else:
                log_callback("move", f"[移动] {md_file.name}\n  {ref}  →  {new_ref}\n")
                if not dry_run:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    moved_files[src_key] = dst

            new_content = re.sub(
                r'(!\[.*?\]\()' + re.escape(ref) + r'(\))',
                r'\g<1>' + new_ref + r'\2',
                new_content
            )
            changed = True
            total_moved += 1

        if changed:
            if not dry_run:
                md_file.write_text(new_content, encoding="utf-8")
            log_callback("ok", f"  ✓ {md_file.name} 引用已更新\n")

    done_callback(total_moved, total_skipped, total_warn, dry_run)
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Obsidian 图片整理工具")
        self.geometry("720x620")
        self.minsize(600, 500)
        self.configure(bg="#1a1a1a")
        self.resizable(True, True)

        # ── 颜色主题 (深色工业风) ──
        self.C = {
            "bg":       "#1a1a1a",
            "surface":  "#242424",
            "surface2": "#2e2e2e",
            "border":   "#383838",
            "accent":   "#7c6af7",
            "accent2":  "#a395f8",
            "green":    "#4ade80",
            "amber":    "#fbbf24",
            "red":      "#f87171",
            "sky":      "#38bdf8",
            "fg":       "#e8e8e8",
            "fg2":      "#999999",
            "fg3":      "#555555",
        }
        C = self.C

        # ── 字体 ──
        self.ft_body  = tkfont.Font(family="Helvetica Neue", size=12)
        self.ft_small = tkfont.Font(family="Helvetica Neue", size=11)
        self.ft_mono  = tkfont.Font(family="Menlo" if os.name != "nt" else "Consolas", size=11)
        self.ft_head  = tkfont.Font(family="Helvetica Neue", size=14, weight="bold")
        self.ft_title = tkfont.Font(family="Helvetica Neue", size=18, weight="bold")

        self._build_ui()

    # ──────────────────────────────────────────
    def _build_ui(self):
        C = self.C

        # ── 顶部标题栏 ──
        top = tk.Frame(self, bg=C["surface"], height=56)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="⬡", font=("Helvetica Neue", 22),
                 bg=C["accent"], fg="white",
                 width=2, padx=6).pack(side="left", padx=(16,10), pady=8)

        tk.Label(top, text="Obsidian 图片整理", font=self.ft_title,
                 bg=C["surface"], fg=C["fg"]).pack(side="left", pady=8)

        self.mode_lbl = tk.Label(top, text="● 预览模式",
                                  font=self.ft_small,
                                  bg=C["surface"], fg=C["amber"])
        self.mode_lbl.pack(side="right", padx=16)

        # ── 主内容区 ──
        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # —— 路径选择 ——
        path_frame = self._section(main, "Vault 根目录")
        inner = tk.Frame(path_frame, bg=C["surface2"])
        inner.pack(fill="x", padx=12, pady=(0,12))

        self.vault_var = tk.StringVar()
        entry = tk.Entry(inner, textvariable=self.vault_var,
                         font=self.ft_mono,
                         bg=C["surface2"], fg=C["fg"],
                         insertbackground=C["accent"],
                         relief="flat", bd=0,
                         highlightthickness=1,
                         highlightbackground=C["border"],
                         highlightcolor=C["accent"])
        entry.pack(side="left", fill="x", expand=True,
                   ipady=8, padx=(10,0))

        self._btn(inner, "浏览…", self._browse, small=True).pack(
            side="right", padx=8, pady=6)

        # —— 选项 ——
        opt_frame = self._section(main, "选项")
        opts_inner = tk.Frame(opt_frame, bg=C["surface2"])
        opts_inner.pack(fill="x", padx=12, pady=(0,12))

        self.dry_run    = self._toggle(opts_inner, "预览模式（Dry Run）",
                                        "只显示变更计划，不实际移动文件或修改笔记", True)
        self.copy_shared= self._toggle(opts_inner, "多笔记共用图片时复制而非移动",
                                        "防止共享图片被移走后其他笔记引用失效", True)
        self.recursive  = self._toggle(opts_inner, "递归处理所有子文件夹",
                                        "同时整理 Vault 内所有子目录中的笔记", True)

        self.dry_run.trace_add("write", self._on_dry_toggle)

        # —— 操作按钮 ——
        btn_row = tk.Frame(main, bg=C["bg"])
        btn_row.pack(fill="x", pady=(4, 8))

        self.run_btn = self._btn(btn_row, "▶  开始整理", self._run, accent=True)
        self.run_btn.pack(side="left")

        self._btn(btn_row, "清空日志", self._clear_log).pack(side="right")

        # —— 日志 ——
        log_frame = self._section(main, "运行日志")
        self.log = scrolledtext.ScrolledText(
            log_frame,
            font=self.ft_mono,
            bg=C["surface2"], fg=C["fg2"],
            insertbackground=C["fg"],
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["border"],
            state="disabled",
            wrap="none",
            height=12,
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=(0,12))
        # 颜色标签
        self.log.tag_config("move",  foreground=C["accent2"])
        self.log.tag_config("copy",  foreground=C["sky"])
        self.log.tag_config("ok",    foreground=C["green"])
        self.log.tag_config("warn",  foreground=C["amber"])
        self.log.tag_config("err",   foreground=C["red"])
        self.log.tag_config("info",  foreground=C["fg2"])
        self.log.tag_config("head",  foreground=C["fg"], font=self.ft_head)
        self.log.tag_config("done",  foreground=C["green"], font=self.ft_head)

        # —— 状态栏 ——
        status = tk.Frame(self, bg=C["surface"], height=28)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(status, textvariable=self.status_var,
                 font=self.ft_small, bg=C["surface"], fg=C["fg3"],
                 anchor="w").pack(side="left", padx=12)

        self._log("info", "填写 Vault 路径后点击「开始整理」。建议先保持预览模式确认无误。\n")

    # ──────────────────────────────────────────
    def _section(self, parent, title):
        C = self.C
        wrap = tk.Frame(parent, bg=C["bg"])
        wrap.pack(fill="x" if title != "运行日志" else "both",
                  expand=(title == "运行日志"),
                  pady=(0, 8))
        lbl = tk.Label(wrap, text=title.upper(),
                       font=tkfont.Font(family="Helvetica Neue", size=9, weight="bold"),
                       bg=C["bg"], fg=C["fg3"])
        lbl.pack(anchor="w", pady=(0, 4))
        box = tk.Frame(wrap, bg=C["surface2"],
                       highlightthickness=1,
                       highlightbackground=C["border"])
        box.pack(fill="both", expand=(title == "运行日志"))
        return box

    def _btn(self, parent, text, cmd, accent=False, small=False):
        C = self.C
        bg = C["accent"] if accent else C["surface"]
        fg = "white" if accent else C["fg"]
        f  = self.ft_small if small else self.ft_body
        b  = tk.Button(parent, text=text, command=cmd,
                       font=f, bg=bg, fg=fg,
                       relief="flat", bd=0, cursor="hand2",
                       activebackground=C["accent2"] if accent else C["surface2"],
                       activeforeground="white" if accent else C["fg"],
                       padx=14, pady=7)
        return b

    def _toggle(self, parent, label, desc, default):
        C = self.C
        var = tk.BooleanVar(value=default)

        # 分隔线（第一行不加）
        if hasattr(self, '_toggle_count'):
            self._toggle_count += 1
            sep = tk.Frame(parent, bg=C["border"], height=1)
            sep.pack(fill="x", padx=10)
        else:
            self._toggle_count = 0

        row = tk.Frame(parent, bg=C["surface2"])
        row.pack(fill="x", padx=10, pady=14)

        # 左侧文字
        left = tk.Frame(row, bg=C["surface2"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=label,
                 font=tkfont.Font(family="Helvetica Neue", size=13, weight="bold"),
                 bg=C["surface2"], fg=C["fg"], anchor="w").pack(anchor="w")
        tk.Label(left, text=desc, font=self.ft_small,
                 bg=C["surface2"], fg=C["fg3"], anchor="w").pack(anchor="w", pady=(3,0))

        # 右侧：状态徽章 + 自绘开关
        right = tk.Frame(row, bg=C["surface2"])
        right.pack(side="right", padx=(16, 0))

        # 状态文字标签
        state_lbl = tk.Label(right, font=tkfont.Font(family="Helvetica Neue", size=11, weight="bold"),
                              bg=C["surface2"], width=5, anchor="e")
        state_lbl.pack(side="left", padx=(0, 10))

        # Canvas 自绘开关
        TW, TH = 52, 28
        canvas = tk.Canvas(right, width=TW, height=TH,
                           bg=C["surface2"], highlightthickness=0, cursor="hand2")
        canvas.pack(side="left")

        def _draw(val):
            canvas.delete("all")
            track_color = C["accent"] if val else C["border"]
            # 轨道
            r = TH // 2
            canvas.create_oval(0, 0, TH, TH, fill=track_color, outline="")
            canvas.create_oval(TW-TH, 0, TW, TH, fill=track_color, outline="")
            canvas.create_rectangle(r, 0, TW-r, TH, fill=track_color, outline="")
            # 滑块
            knob_x = TW - TH//2 - 3 if val else TH//2 + 3
            canvas.create_oval(knob_x - TH//2 + 4, 3,
                                knob_x + TH//2 - 4, TH - 3,
                                fill="white", outline="")
            # 状态文字
            if val:
                state_lbl.config(text="已开启", fg=C["accent"])
            else:
                state_lbl.config(text="已关闭", fg=C["fg3"])

        def _toggle_click(_=None):
            var.set(not var.get())
            _draw(var.get())

        canvas.bind("<Button-1>", _toggle_click)
        _draw(default)

        return var

    # ──────────────────────────────────────────
    def _browse(self):
        path = filedialog.askdirectory(title="选择 Obsidian Vault 文件夹")
        if path:
            self.vault_var.set(path)

    def _on_dry_toggle(self, *_):
        C = self.C
        if self.dry_run.get():
            self.mode_lbl.config(text="● 预览模式", fg=C["amber"])
        else:
            self.mode_lbl.config(text="● 执行模式", fg=C["red"])

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _log(self, tag, msg):
        """线程安全写日志"""
        def _write():
            self.log.configure(state="normal")
            self.log.insert("end", msg, tag)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _write)

    def _set_status(self, msg):
        self.after(0, lambda: self.status_var.set(msg))

    # ──────────────────────────────────────────
    def _run(self):
        vault = self.vault_var.get().strip()
        if not vault:
            self._log("err", "⚠  请先填写 Vault 路径\n")
            return
        if not Path(vault).is_dir():
            self._log("err", f"⚠  路径不存在: {vault}\n")
            return

        dry   = self.dry_run.get()
        copy  = self.copy_shared.get()
        recur = self.recursive.get()

        mode_str = "预览模式" if dry else "执行模式"
        self._log("head", f"\n{'─'*50}\n")
        self._log("info", f"Vault: {vault}\n")
        self._log("info", f"模式: {mode_str}  |  共享图片{'复制' if copy else '移动'}  |  递归: {'是' if recur else '否'}\n")
        self._log("head", f"{'─'*50}\n\n")

        self.run_btn.config(state="disabled", text="运行中…")
        self._set_status("处理中…")

        def worker():
            process_vault(
                vault, dry, copy, recur,
                log_callback=self._log,
                done_callback=self._on_done
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, moved, skipped, warned, dry_run):
        mode = "（预览）" if dry_run else "（已执行）"
        self._log("done", f"\n✓ 完成 {mode}\n")
        self._log("info", f"  移动/更新: {moved}  |  已跳过: {skipped}  |  警告: {warned}\n")
        if dry_run:
            self._log("warn", "\n  ℹ  预览完成。确认无误后取消勾选「预览模式」再次运行以实际执行。\n")
        self._log("head", f"\n{'─'*50}\n\n")
        self.after(0, lambda: self.run_btn.config(state="normal", text="▶  开始整理"))
        self._set_status(f"完成 — 移动 {moved} 张，警告 {warned} 条")


if __name__ == "__main__":
    app = App()
    app.mainloop()
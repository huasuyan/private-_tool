"""
图片批量重命名工具
功能：
  1. 将 (1).jpg / 1.jpg 等"裸数字/括号数字"格式改为零填充格式（如 001.jpg）
     判断规则：文件名已是零填充纯数字（如 001、0001、00001）则视为已规范，跳过不处理
  2. 检测非规则命名（非连续数字序列）的文件夹并列表展示
"""

import os
import re
import csv
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime


# ─────────────────────────────────────────────
#  核心逻辑层
# ─────────────────────────────────────────────

SUPPORTED_EXTS_DEFAULT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# 匹配所有数字类文件名：括号包裹 (1)(10) 或裸数字 1/10/001/00001
ANY_NUM = re.compile(r"^\(?(\d+)\)?$")


def extract_num(stem: str):
    """从文件名主体提取整数值，非数字格式返回 None"""
    m = ANY_NUM.match(stem.strip())
    return int(m.group(1)) if m else None


def folder_needs_rename(stems: list) -> bool:
    """
    判断一组文件名（主体部分）是否需要重命名。
    核心逻辑：字典序排列 == 数字序排列 → 不需要重命名（显示顺序正常）
              字典序排列 != 数字序排列 → 需要重命名

    例：
      ["1","2","10"]  字典序=[1,10,2]  数字序=[1,2,10]  → 不一致 → 需要重命名
      ["01","02","10"] 字典序=[01,02,10] 数字序=[01,02,10] → 一致  → 跳过
      ["001","002","010"] → 同上 → 跳过
    """
    lex_order = sorted(stems)           # 字典序（文件管理器实际显示顺序）
    num_order = sorted(stems, key=lambda s: extract_num(s))  # 数字序
    return lex_order != num_order


def calc_pad(numbers: list) -> int:
    """根据文件夹内最大数字计算所需的最小零填充位数，使字典序=数字序"""
    max_n = max(numbers)
    # 位数至少要能让最大数字不产生乱序
    digits = len(str(max_n))
    return digits


def scan_rename_preview(root_dir: str, exts: set, pad: int, recursive: bool):
    """
    返回待重命名条目列表：
    [{"folder": str, "old": str, "new": str, "conflict": bool}, ...]

    判断逻辑（以文件夹为单位）：
    1. 收集文件夹内所有数字命名图片
    2. 判断当前字典序是否与数字序一致
    3. 不一致 → 整个文件夹的数字图片全部重命名为 zfill(pad) 格式
    4. 一致   → 跳过整个文件夹（无论位数多少）
    """
    results = []

    for dirpath, dirnames, filenames in (os.walk(root_dir) if recursive else _single_level(root_dir)):
        images = [f for f in filenames if os.path.splitext(f)[1].lower() in exts]

        # 分离出数字命名的图片
        numeric_images = []
        for fname in images:
            stem, ext = os.path.splitext(fname)
            n = extract_num(stem)
            if n is not None:
                numeric_images.append((fname, stem, ext.lower(), n))

        if not numeric_images:
            continue

        stems = [stem for _, stem, _, _ in numeric_images]

        # 核心判断：字典序 vs 数字序
        if not folder_needs_rename(stems):
            continue  # 显示顺序已正常，跳过整个文件夹

        # 计算目标零填充位数：取用户设置和最小需求的较大值
        numbers = [n for _, _, _, n in numeric_images]
        min_pad = calc_pad(numbers)
        effective_pad = max(pad, min_pad)

        for fname, stem, ext, n in numeric_images:
            new_name = str(n).zfill(effective_pad) + ext
            if new_name == fname:
                continue
            conflict = os.path.exists(os.path.join(dirpath, new_name))
            results.append({
                "folder": dirpath,
                "old": fname,
                "new": new_name,
                "conflict": conflict,
            })
    return results


def _single_level(root_dir):
    """os.walk 的单层替代，yield (dirpath, dirnames, filenames)"""
    try:
        entries = os.listdir(root_dir)
    except PermissionError:
        return
    filenames = [e for e in entries if os.path.isfile(os.path.join(root_dir, e))]
    dirnames = [e for e in entries if os.path.isdir(os.path.join(root_dir, e))]
    yield root_dir, dirnames, filenames


def execute_rename(items: list, backup: bool, backup_path: str, progress_cb=None):
    """
    执行重命名，返回 (成功数, 跳过数, 错误列表)
    progress_cb(current, total) 可选回调
    """
    ok, skip, errors = 0, 0, []
    if backup:
        _write_backup(items, backup_path)

    total = len(items)
    for i, item in enumerate(items):
        if item["conflict"]:
            skip += 1
        else:
            src = os.path.join(item["folder"], item["old"])
            dst = os.path.join(item["folder"], item["new"])
            try:
                os.rename(src, dst)
                ok += 1
            except Exception as e:
                errors.append(f"{src} → {dst}: {e}")
        if progress_cb:
            progress_cb(i + 1, total)
    return ok, skip, errors


def _write_backup(items, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件夹", "原文件名", "新文件名", "冲突"])
        for it in items:
            w.writerow([it["folder"], it["old"], it["new"], "是" if it["conflict"] else "否"])


def detect_irregular(root_dir: str, exts: set, recursive: bool, allow_gap: int):
    """
    检测非规则命名文件夹。
    返回 [{"path": str, "count": int, "reason": str}, ...]
    """
    results = []
    walker = os.walk(root_dir) if recursive else _single_level(root_dir)

    for dirpath, dirnames, filenames in (os.walk(root_dir) if recursive else _single_level(root_dir)):
        images = [f for f in filenames if os.path.splitext(f)[1].lower() in exts]
        count = len(images)

        if count == 0:
            results.append({"path": dirpath, "count": 0, "reason": "文件夹内无图片"})
            continue

        numbers = []
        non_numeric = []
        for fname in images:
            stem = os.path.splitext(fname)[0]
            n = extract_num(stem)
            if n is not None:
                numbers.append(n)
            else:
                non_numeric.append(fname)

        if non_numeric:
            sample = ", ".join(non_numeric[:3])
            results.append({
                "path": dirpath,
                "count": count,
                "reason": f"含非数字文件名：{sample}{'...' if len(non_numeric) > 3 else ''}",
            })
            continue

        numbers.sort()
        gaps = []
        for a, b in zip(numbers, numbers[1:]):
            if b - a - 1 > allow_gap:
                gaps.append(f"{a}→{b}")
        if gaps:
            results.append({
                "path": dirpath,
                "count": count,
                "reason": f"序号不连续（跳号）：{', '.join(gaps[:3])}{'...' if len(gaps) > 3 else ''}",
            })

    return results


def export_list(data: list, keys: list, headers: list, filepath: str):
    """通用导出 CSV / TXT"""
    ext = os.path.splitext(filepath)[1].lower()
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        if ext == ".csv":
            w = csv.writer(f)
            w.writerow(headers)
            for row in data:
                w.writerow([row.get(k, "") for k in keys])
        else:
            f.write("\t".join(headers) + "\n")
            for row in data:
                f.write("\t".join(str(row.get(k, "")) for k in keys) + "\n")


# ─────────────────────────────────────────────
#  设置对话框
# ─────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings: dict):
        super().__init__(parent)
        self.title("设置")
        self.resizable(False, False)
        self.grab_set()
        self.settings = settings.copy()
        self._build()
        self.wait_window()

    def _build(self):
        pad = dict(padx=12, pady=6)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        # 零填充位数
        ttk.Label(frm, text="零填充位数（2~6）：").grid(row=0, column=0, sticky="w", **pad)
        self._pad_var = tk.IntVar(value=self.settings["pad"])
        ttk.Spinbox(frm, from_=2, to=6, textvariable=self._pad_var, width=6).grid(row=0, column=1, sticky="w", **pad)

        # 图片格式
        ttk.Label(frm, text="支持图片格式：").grid(row=1, column=0, sticky="nw", **pad)
        ext_frm = ttk.Frame(frm)
        ext_frm.grid(row=1, column=1, sticky="w", **pad)
        all_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]
        self._ext_vars = {}
        for i, e in enumerate(all_exts):
            v = tk.BooleanVar(value=e in self.settings["exts"])
            self._ext_vars[e] = v
            ttk.Checkbutton(ext_frm, text=e, variable=v).grid(row=i // 3, column=i % 3, sticky="w")

        # 递归子目录
        ttk.Label(frm, text="递归扫描子目录：").grid(row=2, column=0, sticky="w", **pad)
        self._recursive_var = tk.BooleanVar(value=self.settings["recursive"])
        ttk.Checkbutton(frm, variable=self._recursive_var).grid(row=2, column=1, sticky="w", **pad)

        # 允许跳号数
        ttk.Label(frm, text="允许跳号数（连续性判断）：").grid(row=3, column=0, sticky="w", **pad)
        self._gap_var = tk.IntVar(value=self.settings["allow_gap"])
        ttk.Spinbox(frm, from_=0, to=99, textvariable=self._gap_var, width=6).grid(row=3, column=1, sticky="w", **pad)

        # 自动备份
        ttk.Label(frm, text="操作前自动备份文件名：").grid(row=4, column=0, sticky="w", **pad)
        self._backup_var = tk.BooleanVar(value=self.settings["backup"])
        ttk.Checkbutton(frm, variable=self._backup_var).grid(row=4, column=1, sticky="w", **pad)

        # 按钮
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frm, text="保存", command=self._save).pack(side="left", padx=8)
        ttk.Button(btn_frm, text="取消", command=self.destroy).pack(side="left", padx=8)

    def _save(self):
        self.settings["pad"] = self._pad_var.get()
        self.settings["exts"] = {e for e, v in self._ext_vars.items() if v.get()}
        self.settings["recursive"] = self._recursive_var.get()
        self.settings["allow_gap"] = self._gap_var.get()
        self.settings["backup"] = self._backup_var.get()
        self.destroy()


# ─────────────────────────────────────────────
#  主窗口
# ─────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图片批量重命名工具")
        self.geometry("920x640")
        self.minsize(800, 560)

        self.settings = {
            "pad": 3,
            "exts": set(SUPPORTED_EXTS_DEFAULT),
            "recursive": True,
            "allow_gap": 0,
            "backup": True,
        }

        self._preview_data = []   # Tab1 预览数据
        self._irregular_data = [] # Tab2 检测数据

        self._build_menu()
        self._build_ui()

    # ── 菜单 ──────────────────────────────────
    def _build_menu(self):
        menu = tk.Menu(self)
        self.config(menu=menu)
        tools = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="工具", menu=tools)
        tools.add_command(label="设置", command=self._open_settings)
        tools.add_separator()
        tools.add_command(label="退出", command=self.quit)

    # ── 主界面 ────────────────────────────────
    def _build_ui(self):
        # 顶部路径区
        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")

        ttk.Label(top, text="根目录：").pack(side="left")
        self._dir_var = tk.StringVar()
        ttk.Entry(top, textvariable=self._dir_var, width=55).pack(side="left", padx=4)
        ttk.Button(top, text="选择文件夹", command=self._choose_dir).pack(side="left", padx=4)
        ttk.Button(top, text="扫  描", command=self._scan_all, width=8).pack(side="left", padx=4)

        # Tab 控件
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self._tab1 = ttk.Frame(nb)
        self._tab2 = ttk.Frame(nb)
        nb.add(self._tab1, text="  重命名工具  ")
        nb.add(self._tab2, text="  非规则文件夹检测  ")

        self._build_tab1()
        self._build_tab2()

        # 状态栏
        self._status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self, textvariable=self._status_var,
                               relief="sunken", anchor="w", padding=(8, 2))
        status_bar.pack(fill="x", side="bottom")

        self._progress = ttk.Progressbar(self, mode="determinate")
        self._progress.pack(fill="x", side="bottom")

    # ── Tab1：重命名工具 ───────────────────────
    def _build_tab1(self):
        # 选项行
        opt = ttk.Frame(self._tab1, padding=(8, 6))
        opt.pack(fill="x")

        ttk.Label(opt, text="零填充位数：").pack(side="left")
        self._pad_var = tk.IntVar(value=self.settings["pad"])
        ttk.Spinbox(opt, from_=2, to=6, textvariable=self._pad_var, width=5).pack(side="left", padx=4)

        ttk.Separator(opt, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(opt, text="格式：").pack(side="left")

        all_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]
        self._ext_vars = {}
        for e in all_exts:
            v = tk.BooleanVar(value=True)
            self._ext_vars[e] = v
            ttk.Checkbutton(opt, text=e, variable=v).pack(side="left")

        # 预览表格
        cols = ("folder", "old", "new", "status")
        headers = ("文件夹", "原文件名", "新文件名", "状态")
        self._tree1 = self._make_tree(self._tab1, cols, headers, col_widths=[380, 160, 160, 70])

        # 底部按钮
        btn = ttk.Frame(self._tab1, padding=(8, 6))
        btn.pack(fill="x")
        ttk.Button(btn, text="预览（Dry Run）", command=self._preview).pack(side="left", padx=6)
        ttk.Button(btn, text="执行重命名", command=self._execute_rename).pack(side="left", padx=6)
        ttk.Button(btn, text="导出日志", command=self._export_rename_log).pack(side="left", padx=6)

    # ── Tab2：非规则检测 ───────────────────────
    def _build_tab2(self):
        cols = ("path", "count", "reason")
        headers = ("文件夹路径", "图片数", "非规则原因")
        self._tree2 = self._make_tree(self._tab2, cols, headers, col_widths=[480, 70, 280])
        self._tree2.bind("<Double-1>", self._open_folder_in_explorer)

        btn = ttk.Frame(self._tab2, padding=(8, 6))
        btn.pack(fill="x")
        ttk.Button(btn, text="刷新检测", command=self._detect_irregular).pack(side="left", padx=6)
        ttk.Button(btn, text="导出结果", command=self._export_irregular).pack(side="left", padx=6)
        ttk.Label(btn, text="双击列表项在文件管理器中打开文件夹",
                  foreground="gray").pack(side="right", padx=10)

    # ── 通用 Treeview ─────────────────────────
    def _make_tree(self, parent, cols, headers, col_widths=None):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        sb_y = ttk.Scrollbar(frame, orient="vertical")
        sb_x = ttk.Scrollbar(frame, orient="horizontal")
        tree = ttk.Treeview(frame, columns=cols, show="headings",
                            yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.config(command=tree.yview)
        sb_x.config(command=tree.xview)

        for i, (col, hdr) in enumerate(zip(cols, headers)):
            w = col_widths[i] if col_widths and i < len(col_widths) else 120
            tree.heading(col, text=hdr)
            tree.column(col, width=w, minwidth=60, anchor="w")

        tree.tag_configure("conflict", foreground="red")

        tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    # ── 操作：选择文件夹 ──────────────────────
    def _choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self._dir_var.set(d)

    # ── 操作：扫描（同时刷新两个 Tab）─────────
    def _scan_all(self):
        self._preview()
        self._detect_irregular()

    # ── 操作：预览重命名 ──────────────────────
    def _preview(self):
        root = self._dir_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("提示", "请先选择有效的根目录")
            return

        exts = {e for e, v in self._ext_vars.items() if v.get()}
        pad = self._pad_var.get()
        recursive = self.settings["recursive"]

        self._set_status("正在扫描...")
        self._progress["value"] = 0

        def run():
            data = scan_rename_preview(root, exts, pad, recursive)
            self.after(0, lambda: self._fill_tree1(data))

        threading.Thread(target=run, daemon=True).start()

    def _fill_tree1(self, data):
        self._preview_data = data
        for row in self._tree1.get_children():
            self._tree1.delete(row)
        for item in data:
            tag = "conflict" if item["conflict"] else ""
            status = "⚠ 冲突" if item["conflict"] else "✓ 正常"
            self._tree1.insert("", "end",
                               values=(item["folder"], item["old"], item["new"], status),
                               tags=(tag,))
        self._set_status(f"预览完成：共 {len(data)} 项待重命名，"
                         f"其中 {sum(1 for d in data if d['conflict'])} 项冲突")
        self._progress["value"] = 100

    # ── 操作：执行重命名 ──────────────────────
    def _execute_rename(self):
        if not self._preview_data:
            messagebox.showinfo("提示", "请先执行预览")
            return
        if not messagebox.askyesno("确认", f"将执行 {len(self._preview_data)} 项重命名（冲突项自动跳过），确认吗？"):
            return

        backup_path = ""
        if self.settings["backup"]:
            root = self._dir_var.get().strip()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(root, f"rename_backup_{ts}.csv")

        self._set_status("重命名中...")
        self._progress["value"] = 0

        def run():
            def cb(cur, total):
                self.after(0, lambda: self._set_progress(cur, total))

            ok, skip, errors = execute_rename(
                self._preview_data, self.settings["backup"], backup_path, progress_cb=cb
            )
            self.after(0, lambda: self._rename_done(ok, skip, errors))

        threading.Thread(target=run, daemon=True).start()

    def _rename_done(self, ok, skip, errors):
        msg = f"完成！重命名 {ok} 个文件，跳过冲突 {skip} 个"
        if errors:
            msg += f"，失败 {len(errors)} 个"
            messagebox.showerror("部分失败", "\n".join(errors[:10]))
        self._set_status(msg)
        self._preview_data = []
        for row in self._tree1.get_children():
            self._tree1.delete(row)

    # ── 操作：导出重命名日志 ──────────────────
    def _export_rename_log(self):
        if not self._preview_data:
            messagebox.showinfo("提示", "无数据可导出，请先预览")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("文本文件", "*.txt")],
            initialfile="rename_log.csv",
        )
        if path:
            export_list(self._preview_data,
                        ["folder", "old", "new", "conflict"],
                        ["文件夹", "原文件名", "新文件名", "冲突"],
                        path)
            self._set_status(f"日志已导出：{path}")

    # ── 操作：检测非规则 ──────────────────────
    def _detect_irregular(self):
        root = self._dir_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("提示", "请先选择有效的根目录")
            return

        exts = {e for e, v in self._ext_vars.items() if v.get()}
        self._set_status("检测中...")

        def run():
            data = detect_irregular(root, exts, self.settings["recursive"], self.settings["allow_gap"])
            self.after(0, lambda: self._fill_tree2(data))

        threading.Thread(target=run, daemon=True).start()

    def _fill_tree2(self, data):
        self._irregular_data = data
        for row in self._tree2.get_children():
            self._tree2.delete(row)
        for item in data:
            self._tree2.insert("", "end", values=(item["path"], item["count"], item["reason"]))
        self._set_status(f"检测完成：发现 {len(data)} 个非规则文件夹")

    # ── 操作：在文件管理器中打开 ──────────────
    def _open_folder_in_explorer(self, event):
        sel = self._tree2.selection()
        if not sel:
            return
        path = self._tree2.item(sel[0])["values"][0]
        if not os.path.isdir(path):
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ── 操作：导出非规则结果 ──────────────────
    def _export_irregular(self):
        if not self._irregular_data:
            messagebox.showinfo("提示", "无数据可导出，请先检测")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("文本文件", "*.txt")],
            initialfile="irregular_folders.csv",
        )
        if path:
            export_list(self._irregular_data,
                        ["path", "count", "reason"],
                        ["文件夹路径", "图片数量", "非规则原因"],
                        path)
            self._set_status(f"结果已导出：{path}")

    # ── 设置 ─────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        self.settings = dlg.settings
        # 同步零填充位数到 Tab1 Spinbox
        self._pad_var.set(self.settings["pad"])

    # ── 辅助 ─────────────────────────────────
    def _set_status(self, msg: str):
        self._status_var.set(msg)
        self.update_idletasks()

    def _set_progress(self, cur, total):
        self._progress["value"] = int(cur / total * 100) if total else 0
        self._set_status(f"正在处理... {cur}/{total}")


# ─────────────────────────────────────────────
#  入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
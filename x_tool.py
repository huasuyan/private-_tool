"""
X Tool  v5  — Python GUI + Edge CDP
修复：1)配置持久化  2)【】格式  3)下载重命名选项  4)预览窗口  5)停止修复  6)Edge启动修复
依赖：pip install playwright imagehash Pillow requests tkcalendar
      playwright install chromium
"""

# ── DPI 感知（必须在 tkinter 之前）────────────────────
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading, re, requests, hashlib, time, queue, subprocess, os, json
from pathlib import Path
from datetime import datetime, date
from io import BytesIO

try:
    from PIL import Image, ImageTk
    import imagehash
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from tkcalendar import DateEntry
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ── DPI scale ─────────────────────────────────────────
def _dpi_scale():
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0
SCALE = _dpi_scale()

# ── Paths ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "xtool_config.json"
BAT_FILE    = SCRIPT_DIR / "启动edge调试模式.bat"

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
CDP_PORT = 9222

# ── Colors ────────────────────────────────────────────
BG      = "#0f1117"
BG2     = "#1a1d27"
BG3     = "#252836"
ACCENT  = "#1d9bf0"
ACCENT2 = "#0d7cc7"
SUCCESS = "#00ba7c"
WARNING = "#ffd400"
ERROR   = "#f4212e"
TEXT    = "#e7e9ea"
TEXT2   = "#71767b"
BORDER  = "#2f3336"

F     = ("Segoe UI", 10)
FB    = ("Segoe UI", 10, "bold")
FS    = ("Segoe UI",  9)
FM    = ("Consolas", 10)
FHEAD = ("Segoe UI", 18, "bold")

# ── Rename format options (shared by both modes) ──────
RENAME_OPTS = [
    ("【{display_name}】",              "【昵称】"),
    ("【@{username}】",                 "【@用户名】"),
    ("【{display_name}(@{username})】", "【昵称(@用户名)】"),
    ("{display_name}",                  "昵称（无括号）"),
    ("@{username}",                     "@用户名（无括号）"),
]

# ── Config persistence ────────────────────────────────
DEFAULT_CFG = {
    "dl_user":        "",
    "dl_dir":         "",
    "dl_filter_mode": "count",
    "dl_count":       "20",
    "dl_max_scroll":  "200",
    "dl_scroll_delay":"2.5",
    "dl_rename_fmt":  "【{display_name}】",
    "rn_user":        "",
    "rn_dir":         "",
    "rn_scroll_times":"30",
    "rn_scroll_delay":"2.5",
    "rn_threshold":   "10",
    "rn_dry_run":     True,
    "rn_rename_fmt":  "【{display_name}】",
}

def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            cfg  = DEFAULT_CFG.copy()
            cfg.update(data)
            return cfg
    except Exception:
        pass
    return DEFAULT_CFG.copy()

def save_config(data: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding='utf-8')
    except Exception:
        pass

# ── Helpers ───────────────────────────────────────────
def sanitize(name: str, max_len=55) -> str:
    """Remove illegal filename chars but preserve 【】"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name).strip('. ')
    return (name or "unknown")[:max_len]

def apply_fmt(fmt: str, display_name: str, username: str) -> str:
    return fmt.format(display_name=display_name or username or "unknown",
                      username=username or "unknown")

def make_unique(stem: str, suffix: str, used: set) -> str:
    c = f"{stem}{suffix}"
    if c not in used: return c
    i = 2
    while True:
        c = f"{stem}_{i}{suffix}"
        if c not in used: return c
        i += 1

def find_edge():
    for p in EDGE_PATHS:
        if os.path.exists(p): return p
    return None

def is_cdp_running():
    try:
        r = requests.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def launch_edge_debug():
    """Try .bat first, then direct subprocess."""
    # Try bat file in same directory
    if BAT_FILE.exists():
        try:
            subprocess.Popen(
                ['cmd', '/c', str(BAT_FILE)],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            return True
        except Exception:
            pass
    # Direct launch
    edge = find_edge()
    if not edge:
        return False
    try:
        # Kill existing Edge first (required for CDP mode)
        subprocess.run(['taskkill', '/f', '/im', 'msedge.exe'],
                       capture_output=True)
        time.sleep(1)
        subprocess.Popen(
            [edge,
             f"--remote-debugging-port={CDP_PORT}",
             "--no-first-run",
             "--no-default-browser-check",
             "https://x.com/login"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════
#  Worker  (background thread)
# ══════════════════════════════════════════════════════
class XWorker:
    def __init__(self, q: queue.Queue):
        self.q      = q
        self._stop  = False   # FIX #5: checked inside tight loops

    def stop(self):
        self._stop = True

    def log(self, m, t="info"): self.q.put(("log",      m, t))
    def progress(self, v, mx):  self.q.put(("progress",  v, mx))
    def status(self, m):        self.q.put(("status",    m))
    def ask_ready(self, ev):    self.q.put(("ask_ready", ev))

    def _connect_edge(self, p):
        if not is_cdp_running():
            self.log("Edge 调试模式未运行，请先点击「启动 Edge 调试模式」", "error")
            return None, None, None
        self.log(f"已连接 Edge (CDP:{CDP_PORT})", "success")
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx  = browser.contexts[0] if browser.contexts else browser.new_context()
        page = None
        for pg in ctx.pages:
            if 'x.com' in pg.url or 'twitter.com' in pg.url:
                page = pg; break
        if page is None:
            page = ctx.new_page()
        return browser, ctx, page

    def _username(self, el):
        try:
            for a in el.query_selector_all('a[href^="/"]'):
                href = a.get_attribute('href') or ''
                m = re.match(r'^/([A-Za-z0-9_]{1,50})$', href)
                if m and m.group(1) not in {
                    'i','home','explore','notifications',
                    'messages','search','settings','compose'
                }:
                    return m.group(1)
        except Exception: pass
        return None

    def _display(self, el):
        try:
            node = el.query_selector('[data-testid="User-Name"]')
            if node:
                for s in node.query_selector_all('span'):
                    t = s.inner_text().strip()
                    if t and not t.startswith('@'): return t
        except Exception: pass
        return None

    def _tweet_date(self, el):
        try:
            te = el.query_selector('time')
            if te:
                ds = te.get_attribute('datetime') or ''
                if ds: return datetime.fromisoformat(ds.replace('Z', '+00:00'))
        except Exception: pass
        return None

    def _goto_likes(self, page, username):
        url = f"https://x.com/{username}/likes"
        self.log(f"跳转：{url}")
        self.status("加载 Likes 页面...")
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        time.sleep(2)
        try:
            page.wait_for_selector('[data-testid="tweet"]', timeout=20000)
        except Exception:
            self.log("未检测到推文内容，请确认 Edge 已登录且用户名正确", "error")
            return False
        self.log("✅ Likes 页面就绪", "success")
        return True

    # ── Mode 1: Download ───────────────────────────
    def run_download(self, cfg):
        username     = cfg['username']
        save_dir     = Path(cfg['save_dir'])
        mode         = cfg['filter_mode']   # 'count' | 'manual'
        count_limit  = cfg.get('count_limit', 20)
        scroll_delay = cfg.get('scroll_delay', 2.5)
        max_scroll   = cfg.get('max_scroll', 500)
        rename_fmt   = cfg.get('rename_fmt', '【{display_name}】')
        # manual mode: caller sets this Event when user clicks "停止收集"
        stop_collect = cfg.get('stop_collect_event')   # threading.Event or None

        save_dir.mkdir(parents=True, exist_ok=True)
        collected, seen = [], set()

        ready_event = threading.Event()
        self.ask_ready(ready_event)
        ready_event.wait()
        if self._stop: self.q.put(("done", False)); return

        try:
            with sync_playwright() as p:
                browser, ctx, page = self._connect_edge(p)
                if browser is None: self.q.put(("done", False)); return
                if not self._goto_likes(page, username):
                    self.q.put(("done", False)); return

                if mode == 'manual':
                    # Notify GUI to show the "停止收集" button
                    self.q.put(("show_stop_collect",))
                    self.log("📜  手动模式：页面将持续滚动收集图片", "info")
                    self.log("    收集完你想要的范围后，点击【停止收集并开始下载】", "warn")

                done, sc = False, 0
                while not done and not self._stop and sc < max_scroll:
                    for tw in page.query_selector_all('[data-testid="tweet"]'):
                        if self._stop: done = True; break
                        uname = self._username(tw)
                        dname = self._display(tw)
                        for img in tw.query_selector_all('img[src*="pbs.twimg.com/media"]'):
                            if self._stop: break
                            src  = img.get_attribute('src') or ''
                            base = src.split('?')[0]
                            if base in seen: continue
                            seen.add(base)
                            collected.append({
                                'orig_url':     base + '?format=jpg&name=orig',
                                'username':     uname or 'unknown',
                                'display_name': dname or uname or 'unknown',
                            })

                    if mode == 'count' and len(collected) >= count_limit:
                        done = True

                    # manual mode: check if user clicked "停止收集"
                    if mode == 'manual' and stop_collect and stop_collect.is_set():
                        self.log(f"收集阶段结束，共找到 {len(collected)} 张", "warn")
                        done = True

                    if not done and not self._stop:
                        page.evaluate("window.scrollBy(0, window.innerHeight*2.5)")
                        for _ in range(int(scroll_delay * 4)):
                            if self._stop: break
                            if mode == 'manual' and stop_collect and stop_collect.is_set():
                                break
                            time.sleep(0.25)
                        sc += 1
                        self.status(f"滚动第{sc}次 | 已找到{len(collected)}张")
                        self.log(f"  第{sc}次滚动，已收集{len(collected)}张", "info")

                # Hide "停止收集" button once scrolling is done
                if mode == 'manual':
                    self.q.put(("hide_stop_collect",))

        except Exception as e:
            self.log(f"错误：{e}", "error")
            self.q.put(("hide_stop_collect",))
            self.q.put(("done", False)); return

        if self._stop:
            self.log("已停止", "warn")
            self.q.put(("hide_stop_collect",))
            self.q.put(("done", False)); return

        if mode == 'count':
            collected = collected[:count_limit]

        if not collected:
            self.log("未找到图片", "error"); self.q.put(("done", False)); return

        self.log(f"\n共 {len(collected)} 张，开始下载原图...\n", "success")
        self.progress(0, len(collected))
        headers = {'User-Agent': 'Mozilla/5.0'}
        used, ok = set(), 0
        failed   = []   # list of (item, stem, error_str)

        # ── First pass ────────────────────────────
        for i, item in enumerate(collected):
            if self._stop: break
            raw  = apply_fmt(rename_fmt, item['display_name'], item['username'])
            stem = make_unique(sanitize(raw), '.jpg', used)
            used.add(stem)
            try:
                r = requests.get(item['orig_url'], headers=headers, timeout=20)
                r.raise_for_status()
                (save_dir / stem).write_bytes(r.content)
                ok += 1
                self.log(f"  ✅[{i+1}/{len(collected)}] {stem}", "success")
            except Exception as e:
                err = str(e)
                self.log(f"  ❌[{i+1}/{len(collected)}] {stem}  ({err})", "error")
                failed.append({'item': item, 'stem': stem, 'error': err})
            self.progress(i+1, len(collected))
            self.status(f"下载 {i+1}/{len(collected)}")

        # ── Retry failed items ────────────────────
        if failed and not self._stop:
            self.log(f"\n🔄  开始重试 {len(failed)} 个失败项...\n", "warn")
            still_failed = []
            self.progress(0, len(failed))
            for i, entry in enumerate(failed):
                if self._stop: break
                item = entry['item']
                stem = entry['stem']
                # Make sure stem is still unique (file may or may not exist)
                dest = save_dir / stem
                try:
                    time.sleep(1)   # brief pause before retry
                    r = requests.get(item['orig_url'], headers=headers, timeout=30)
                    r.raise_for_status()
                    dest.write_bytes(r.content)
                    ok += 1
                    self.log(f"  ✅ 重试成功[{i+1}/{len(failed)}] {stem}", "success")
                except Exception as e:
                    self.log(f"  ❌ 重试失败[{i+1}/{len(failed)}] {stem}  ({e})", "error")
                    still_failed.append(entry)
                self.progress(i+1, len(failed))
                self.status(f"重试 {i+1}/{len(failed)}")

            # ── Final failure report ──────────────
            if still_failed:
                self.log("\n" + "─"*50, "warn")
                self.log(f"⚠️  最终失败 {len(still_failed)} 张，URL 如下：", "warn")
                for entry in still_failed:
                    self.log(f"  文件名：{entry['stem']}", "warn")
                    self.log(f"  图片URL：{entry['item']['orig_url']}", "warn")
                    self.log(f"  错误：{entry['error']}", "error")
                    self.log("", "info")
                self.log("─"*50, "warn")
                self.log("提示：可复制上方 URL 在浏览器中手动下载", "info")
            else:
                self.log("✅  所有重试均成功！", "success")

        final_failed = len([e for e in failed]) - (ok - (len(collected) - len(failed))) if failed else 0
        self.log(f"\n完成！成功 {ok}/{len(collected)} 张 → {save_dir}", "success")
        self.q.put(("done", True))

    # ── Mode 2: Rename ─────────────────────────────
    def run_rename(self, cfg):
        username     = cfg['username']
        local_dir    = Path(cfg['local_dir'])
        scroll_times = cfg.get('scroll_times', 30)
        scroll_delay = cfg.get('scroll_delay', 2.5)
        threshold    = cfg.get('hash_threshold', 10)
        dry_run      = cfg.get('dry_run', True)
        rename_fmt   = cfg.get('rename_fmt', '【{display_name}】')

        if not PIL_AVAILABLE:
            self.log("缺少 imagehash/Pillow", "error"); self.q.put(("done", False)); return

        exts  = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        local = [p for p in local_dir.iterdir() if p.suffix.lower() in exts]
        if not local:
            self.log("文件夹无图片", "error"); self.q.put(("done", False)); return
        self.log(f"本地图片：{len(local)} 张")

        ready_event = threading.Event()
        self.ask_ready(ready_event)
        ready_event.wait()
        if self._stop: self.q.put(("done", False)); return

        likes, seen = [], set()
        try:
            with sync_playwright() as p:
                browser, ctx, page = self._connect_edge(p)
                if browser is None: self.q.put(("done", False)); return
                if not self._goto_likes(page, username):
                    self.q.put(("done", False)); return

                for i in range(scroll_times):
                    if self._stop: break
                    for tw in page.query_selector_all('[data-testid="tweet"]'):
                        if self._stop: break
                        u = self._username(tw); d = self._display(tw)
                        for img in tw.query_selector_all('img[src*="pbs.twimg.com/media"]'):
                            src  = img.get_attribute('src') or ''
                            base = src.split('?')[0]
                            if base in seen: continue
                            seen.add(base)
                            likes.append({'orig_url': base+'?format=jpg&name=orig',
                                          'thumb_url': src, 'username': u or '',
                                          'display_name': d or u or ''})
                    if not self._stop:
                        page.evaluate("window.scrollBy(0, window.innerHeight*2.5)")
                        for _ in range(int(scroll_delay * 4)):
                            if self._stop: break
                            time.sleep(0.25)
                    self.log(f"  第{i+1}次，已收集{len(likes)}张")
                    self.status(f"爬取第{i+1}/{scroll_times}次 | {len(likes)}张")
        except Exception as e:
            self.log(f"错误：{e}", "error"); self.q.put(("done", False)); return

        if self._stop:
            self.log("已停止", "warn"); self.q.put(("done", False)); return

        if not likes:
            self.log("未获取到图片", "error"); self.q.put(("done", False)); return

        self.log(f"\n获取{len(likes)}张，计算哈希...\n")
        cache = Path("xtool_cache"); cache.mkdir(exist_ok=True)
        headers = {'User-Agent': 'Mozilla/5.0'}
        hashes  = []
        self.progress(0, len(likes))

        for i, item in enumerate(likes):
            if self._stop: break
            url = item.get('orig_url') or item.get('thumb_url', '')
            cp  = cache / f"{hashlib.md5(url.encode()).hexdigest()}.jpg"
            try:
                if cp.exists():
                    img = Image.open(cp).convert('RGB')
                else:
                    r = requests.get(url, headers=headers, timeout=15)
                    r.raise_for_status()
                    img = Image.open(BytesIO(r.content)).convert('RGB')
                    img.save(cp)
                hashes.append((imagehash.phash(img), item))
            except Exception as e:
                self.log(f"  ⚠️ {e}", "warn")
            self.progress(i+1, len(likes))
            self.status(f"哈希 {i+1}/{len(likes)}")

        if self._stop:
            self.log("已停止", "warn"); self.q.put(("done", False)); return

        self.log("\n匹配本地图片...\n")
        used, preview_items = set(), []

        for lp in local:
            if self._stop: break
            try: lh = imagehash.phash(Image.open(lp).convert('RGB'))
            except Exception: self.log(f"  ⚠️ 无法读取 {lp.name}", "warn"); continue
            bd, bi = float('inf'), None
            for rh, item in hashes:
                d = lh - rh
                if d < bd: bd, bi = d, item
            sfx = lp.suffix.lower()
            if bi and bd <= threshold:
                raw  = apply_fmt(rename_fmt, bi.get('display_name',''), bi.get('username',''))
                name = make_unique(sanitize(raw), sfx, used)
                used.add(name)
                self.log(f"  ✓ {lp.name} → {name}  (距离:{bd})", "info")
                preview_items.append({
                    'old_path': str(lp),
                    'new_name': name,
                    'matched':  True,
                    'distance': bd,
                })
            else:
                self.log(f"  ✗ {lp.name}  (未匹配,距离:{bd})", "warn")
                preview_items.append({
                    'old_path': str(lp),
                    'new_name': lp.name,
                    'matched':  False,
                    'distance': bd,
                })

        if dry_run:
            # FIX #4: send preview data to GUI
            self.q.put(("preview", preview_items))
        else:
            matched = 0
            for pi in preview_items:
                if self._stop: break
                if pi['matched']:
                    try:
                        Path(pi['old_path']).rename(
                            Path(pi['old_path']).parent / pi['new_name'])
                        matched += 1
                    except Exception as e:
                        self.log(f"  重命名失败 {pi['old_path']}: {e}", "error")
            self.log(f"\n完成！{matched}/{len(local)} 张成功", "success")
            self.q.put(("done", True))


# ══════════════════════════════════════════════════════
#  Preview Window  (FIX #4)
# ══════════════════════════════════════════════════════
class PreviewWindow(tk.Toplevel):
    def __init__(self, parent, items: list):
        super().__init__(parent)
        self.title("重命名预览  —  选择要应用的图片")
        self.configure(bg=BG)
        try: self.tk.call('tk', 'scaling', SCALE)
        except Exception: pass
        self.geometry("820x620")
        self.minsize(700, 500)

        # Center on parent
        parent.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        self.geometry(f"820x620+{px-410}+{py-310}")

        self._items   = items          # list of dicts
        self._vars    = []             # BooleanVar per row
        self._parent  = parent

        self._build(items)

    def _build(self, items):
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=16, pady=(14,4))
        tk.Label(hdr, text="重命名预览", font=FHEAD, bg=BG, fg=ACCENT).pack(side='left')
        n_matched = sum(1 for i in items if i['matched'])
        tk.Label(hdr, text=f"  {n_matched}/{len(items)} 张匹配",
                 font=F, bg=BG, fg=TEXT2).pack(side='left')

        ttk.Separator(self).pack(fill='x', padx=16, pady=(2,0))

        # Select-all bar
        ctrl = tk.Frame(self, bg=BG2)
        ctrl.pack(fill='x', padx=16, pady=6)
        tk.Button(ctrl, text='全选', bg=BG3, fg=TEXT, relief='flat', font=FS,
                  cursor='hand2', bd=0, activebackground=ACCENT2, activeforeground='white',
                  command=self._select_all).pack(side='left', padx=6, pady=4)
        tk.Button(ctrl, text='全不选', bg=BG3, fg=TEXT, relief='flat', font=FS,
                  cursor='hand2', bd=0, activebackground=BG3, activeforeground=TEXT,
                  command=self._deselect_all).pack(side='left', padx=4, pady=4)
        tk.Button(ctrl, text='只选匹配项', bg=BG3, fg=TEXT, relief='flat', font=FS,
                  cursor='hand2', bd=0, activebackground=ACCENT2, activeforeground='white',
                  command=self._select_matched).pack(side='left', padx=4, pady=4)
        self._count_lbl = tk.Label(ctrl, text="", bg=BG2, fg=TEXT2, font=FS)
        self._count_lbl.pack(side='right', padx=10)

        # Scrollable list
        canvas_frame = tk.Frame(self, bg=BG)
        canvas_frame.pack(fill='both', expand=True, padx=16, pady=(0,4))

        canvas = tk.Canvas(canvas_frame, bg=BG3, highlightthickness=0)
        vsb    = ttk.Scrollbar(canvas_frame, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        inner = tk.Frame(canvas, bg=BG3)
        win_id = canvas.create_window((0,0), window=inner, anchor='nw')

        def _resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind('<Configure>', _resize)
        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), 'units'))

        # Column headers
        hdr_row = tk.Frame(inner, bg=BG2)
        hdr_row.pack(fill='x', padx=4, pady=(4,0))
        tk.Label(hdr_row, text='✓', bg=BG2, fg=TEXT2, font=FS, width=3).pack(side='left', padx=4)
        tk.Label(hdr_row, text='原文件名', bg=BG2, fg=TEXT2, font=FS, width=28, anchor='w').pack(side='left', padx=6)
        tk.Label(hdr_row, text='→', bg=BG2, fg=TEXT2, font=FS).pack(side='left', padx=4)
        tk.Label(hdr_row, text='新文件名', bg=BG2, fg=TEXT2, font=FS, anchor='w').pack(side='left', padx=6)

        self._vars = []
        for idx, item in enumerate(items):
            var = tk.BooleanVar(value=item['matched'])
            self._vars.append(var)
            var.trace_add('write', lambda *a: self._update_count())

            row_bg = BG3 if idx % 2 == 0 else "#20232f"
            row = tk.Frame(inner, bg=row_bg)
            row.pack(fill='x', padx=4, pady=1)

            tk.Checkbutton(row, variable=var, bg=row_bg,
                           fg=TEXT, activebackground=row_bg,
                           activeforeground=TEXT,
                           selectcolor=ACCENT,        # 蓝色勾选框，深色背景下清晰可见
                           relief='flat', bd=0,
                           cursor='hand2').pack(side='left', padx=6)

            old_name = Path(item['old_path']).name
            new_name = item['new_name']
            changed  = old_name != new_name

            old_col = TEXT  if changed else TEXT2
            new_col = SUCCESS if changed else TEXT2
            dist_txt = f"  (d:{item['distance']})" if item['matched'] else "  ✗未匹配"

            tk.Label(row, text=old_name, bg=row_bg, fg=old_col,
                     font=FM, width=28, anchor='w').pack(side='left', padx=6)
            tk.Label(row, text='→', bg=row_bg, fg=TEXT2, font=F).pack(side='left')
            tk.Label(row, text=new_name, bg=row_bg, fg=new_col,
                     font=FM, anchor='w').pack(side='left', padx=6)
            tk.Label(row, text=dist_txt, bg=row_bg, fg=TEXT2,
                     font=FS).pack(side='left', padx=2)

        self._update_count()

        # Bottom buttons
        ttk.Separator(self).pack(fill='x', padx=16, pady=(4,0))
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill='x', padx=16, pady=10)

        tk.Button(btn_row, text='✅  应用选中项', bg=SUCCESS, fg='white',
                  font=FB, relief='flat', cursor='hand2', bd=0, padx=18, pady=9,
                  activebackground='#009e68', activeforeground='white',
                  command=self._apply).pack(side='left')
        tk.Button(btn_row, text='✕  取消', bg=BG3, fg=TEXT2,
                  font=F, relief='flat', cursor='hand2', bd=0, padx=14, pady=9,
                  activebackground=BG2, activeforeground=TEXT,
                  command=self.destroy).pack(side='left', padx=10)

    def _update_count(self):
        n = sum(v.get() for v in self._vars)
        self._count_lbl.configure(text=f"已选 {n} 张")

    def _select_all(self):
        for v in self._vars: v.set(True)

    def _deselect_all(self):
        for v in self._vars: v.set(False)

    def _select_matched(self):
        for v, item in zip(self._vars, self._items):
            v.set(item['matched'])

    def _apply(self):
        applied, skipped = 0, 0
        for var, item in zip(self._vars, self._items):
            if not var.get(): skipped += 1; continue
            old = Path(item['old_path'])
            new = old.parent / item['new_name']
            if old == new: skipped += 1; continue
            try:
                old.rename(new)
                applied += 1
            except Exception as e:
                messagebox.showerror("重命名失败", f"{old.name}\n{e}")
        messagebox.showinfo("完成",
            f"已重命名：{applied} 张\n跳过：{skipped} 张")
        self.destroy()


# ══════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════
class XToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("X Tool  v5  ·  图片下载 & 重命名")
        try: self.tk.call('tk', 'scaling', SCALE)
        except Exception: pass
        self.geometry("1000x1000")
        self.minsize(720, 600)
        self.resizable(True, True)
        self.configure(bg=BG)

        self._cfg     = load_config()
        self._q       = queue.Queue()
        self._worker  = None
        self._running = False
        self._dot_idx = 0

        self._style()
        self._ui()
        self._load_cfg_into_ui()
        self._restore_window_size()
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._save_cfg()
        self.destroy()

    def _restore_window_size(self):
        """Restore window geometry from config if saved."""
        geo = self._cfg.get('window_geometry', '')
        if geo:
            try:
                self.geometry(geo)
                return
            except Exception:
                pass

    # ── ttk style ──────────────────────────────────
    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',                 background=BG,  foreground=TEXT,  font=F)
        s.configure('TFrame',            background=BG)
        s.configure('TLabel',            background=BG,  foreground=TEXT,  font=F)
        s.configure('TLabelframe',       background=BG2, relief='flat',
                    borderwidth=1, bordercolor=BORDER)
        s.configure('TLabelframe.Label', background=BG2, foreground=ACCENT, font=FB)
        s.configure('TNotebook',         background=BG,  tabmargins=[2,5,0,0])
        s.configure('TNotebook.Tab',     background=BG3, foreground=TEXT2,
                    padding=[18,8], font=FB)
        s.map('TNotebook.Tab',
              background=[('selected',BG2),('active',BG3)],
              foreground=[('selected',ACCENT),('active',TEXT)])
        s.configure('TEntry',    fieldbackground=BG3, foreground=TEXT,
                    insertcolor=TEXT, relief='flat', padding=6)
        s.configure('TSpinbox',  fieldbackground=BG3, foreground=TEXT,
                    insertcolor=TEXT, relief='flat', padding=5)
        s.configure('TCheckbutton', background=BG2, foreground=TEXT, indicatorcolor=ACCENT)
        s.map('TCheckbutton', background=[('active',BG2)])
        s.configure('TRadiobutton', background=BG2, foreground=TEXT)
        s.map('TRadiobutton', background=[('active',BG2)])
        s.configure('Run.TButton',  background=ACCENT, foreground='white',
                    font=("Segoe UI",11,"bold"), relief='flat', padding=[28,12])
        s.map('Run.TButton',
              background=[('active',ACCENT2),('disabled',BG3)],
              foreground=[('disabled',TEXT2)])
        s.configure('Stop.TButton', background=ERROR, foreground='white',
                    font=("Segoe UI",11,"bold"), relief='flat', padding=[28,12])
        s.map('Stop.TButton', background=[('active','#c0001f')])
        s.configure('TProgressbar', troughcolor=BG3, background=ACCENT,
                    thickness=6, relief='flat')
        s.configure('TSeparator', background=BORDER)

    # ── main UI ────────────────────────────────────
    def _ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=24, pady=(14,4))
        tk.Label(hdr, text="✦ X Tool", font=FHEAD, bg=BG, fg=ACCENT).pack(side='left')
        tk.Label(hdr, text="  图片下载 & 重命名  ·  Edge 版",
                 font=F, bg=BG, fg=TEXT2).pack(side='left')
        ttk.Separator(self).pack(fill='x', padx=24, pady=(2,0))

        # Edge status bar  (FIX #6)
        edge_bar = tk.Frame(self, bg=BG2)
        edge_bar.pack(fill='x', padx=24, pady=(6,0))
        tk.Label(edge_bar, text="Edge 调试模式：", bg=BG2, fg=TEXT2,
                 font=FS).pack(side='left', padx=10, pady=5)
        self.edge_lbl = tk.Label(edge_bar, text="检测中...", bg=BG2, fg=WARNING, font=FB)
        self.edge_lbl.pack(side='left', pady=5)
        tk.Button(edge_bar, text=' 启动 Edge 调试模式 ',
                  bg=ACCENT, fg='white', relief='flat', font=FS,
                  cursor='hand2', bd=0,
                  activebackground=ACCENT2, activeforeground='white',
                  command=self._launch_edge
                  ).pack(side='right', padx=10, pady=5)
        self._check_edge()

        # Action bar
        act = tk.Frame(self, bg=BG)
        act.pack(fill='x', padx=24, pady=10)
        self.action_btn = ttk.Button(act, text='▶   开始运行',
                                     style='Run.TButton', command=self._toggle)
        self.action_btn.pack(side='left')

        self._ind_frame = tk.Frame(act, bg=BG)
        self._ind_frame.pack(side='left', padx=18)
        self._dot_cv = tk.Canvas(self._ind_frame, width=14, height=14,
                                 bg=BG, highlightthickness=0)
        self._dot_cv.pack(side='left')
        self._dot = self._dot_cv.create_oval(2,2,12,12, fill=BG, outline='')
        tk.Label(self._ind_frame, text="运行中...", bg=BG,
                 fg=WARNING, font=FB).pack(side='left', padx=(6,0))
        self._ind_frame.pack_forget()

        tk.Button(act, text='清空日志', bg=BG3, fg=TEXT2, relief='flat',
                  font=FS, cursor='hand2', bd=0,
                  activebackground=BG2, activeforeground=TEXT,
                  command=lambda: self.log_box.delete('1.0','end')
                  ).pack(side='right', padx=4)

        ttk.Separator(self).pack(fill='x', padx=24)

        # Notebook
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='x', padx=24, pady=(8,0))
        self._tdl = ttk.Frame(self.nb)
        self._trn = ttk.Frame(self.nb)
        self.nb.add(self._tdl, text='  ↓  模式一：从 Likes 下载原图  ')
        self.nb.add(self._trn, text='  ✎  模式二：本地图片重命名  ')
        self._build_dl()
        self._build_rn()

        ttk.Separator(self).pack(fill='x', padx=24, pady=(8,0))

        # Log
        log_lf = ttk.LabelFrame(self, text='  运行日志')
        log_lf.pack(fill='both', expand=True, padx=24, pady=(6,4))
        self.log_box = scrolledtext.ScrolledText(
            log_lf, bg=BG3, fg=TEXT, font=FM, relief='flat', bd=0,
            insertbackground=TEXT, selectbackground=ACCENT, wrap='word', height=16)
        self.log_box.pack(fill='both', expand=True, padx=6, pady=6)
        for tag, col in [('info',TEXT),('success',SUCCESS),('warn',WARNING),('error',ERROR)]:
            self.log_box.tag_config(tag, foreground=col)

        # Status bar
        sb = tk.Frame(self, bg=BG)
        sb.pack(fill='x', padx=24, pady=(2,12))
        self.status_lbl = tk.Label(sb, text="就绪", bg=BG, fg=TEXT2,
                                   font=FS, width=30, anchor='w')
        self.status_lbl.pack(side='left')
        self.prog = ttk.Progressbar(sb, mode='determinate')
        self.prog.pack(side='right', fill='x', expand=True, padx=(8,0))

    # ── Download tab ───────────────────────────────
    def _build_dl(self):
        f   = self._tdl
        pad = dict(padx=12, pady=7)

        bs = ttk.LabelFrame(f, text='  基本设置')
        bs.pack(fill='x', padx=12, pady=(10,4))
        bs.columnconfigure(1, weight=1)
        self._entry_row(bs, 0, 'X 用户名（不含 @）', 'dl_user')
        self._entry_row(bs, 1, '图片保存文件夹',      'dl_dir', browse=True)

        # Filter mode: count only | manual
        fl = ttk.LabelFrame(f, text='  收集模式')
        fl.pack(fill='x', padx=12, pady=4)
        self.dl_mode = tk.StringVar(value='count')

        ttk.Radiobutton(fl, text='前', variable=self.dl_mode, value='count',
                        command=self._dl_toggle).grid(row=0, column=0, sticky='w', **pad)
        self.dl_count = tk.StringVar(value='20')
        ttk.Spinbox(fl, from_=1, to=2000, width=7,
                    textvariable=self.dl_count).grid(row=0, column=1, sticky='w', pady=7)
        tk.Label(fl, text='条推文中的图片', bg=BG2, fg=TEXT,
                 font=F).grid(row=0, column=2, sticky='w', padx=6)

        ttk.Radiobutton(fl, text='手动控制  —  持续滚动，我来决定什么时候停止收集',
                        variable=self.dl_mode, value='manual',
                        command=self._dl_toggle).grid(row=1, column=0, columnspan=4,
                        sticky='w', **pad)

        # "停止收集" button — only visible during manual-mode scrolling
        self._stop_collect_bar = tk.Frame(f, bg="#1a2a1a", relief='flat')
        # (packed/unpacked dynamically by _show/_hide_stop_collect)
        sc_inner = tk.Frame(self._stop_collect_bar, bg="#1a2a1a")
        sc_inner.pack(padx=12, pady=8)
        tk.Label(sc_inner,
                 text="📜  正在持续滚动收集图片，收集到满意范围后点击右侧按钮",
                 bg="#1a2a1a", fg=WARNING, font=F).pack(side='left', padx=(0,12))
        self._stop_collect_btn = tk.Button(
            sc_inner, text='⏹  停止收集并开始下载',
            bg=SUCCESS, fg='white', font=FB, relief='flat',
            cursor='hand2', bd=0, padx=14, pady=7,
            activebackground='#009e68', activeforeground='white',
            command=self._on_stop_collect
        )
        self._stop_collect_btn.pack(side='left')
        self._stop_collect_event = None   # set when manual mode starts

        # Rename format
        rf = ttk.LabelFrame(f, text='  下载文件名格式')
        rf.pack(fill='x', padx=12, pady=4)
        self.dl_rename_fmt = tk.StringVar(value='【{display_name}】')
        for i, (v, l) in enumerate(RENAME_OPTS):
            ttk.Radiobutton(rf, text=l, variable=self.dl_rename_fmt, value=v
                            ).grid(row=i//3, column=i%3, sticky='w', padx=10, pady=4)

        av = ttk.LabelFrame(f, text='  高级设置')
        av.pack(fill='x', padx=12, pady=4)
        self._spin_row(av, 0, '最大自动滚动次数（手动模式亦适用）',
                       'dl_max_scroll',   10, 2000, 500)
        self._spin_row(av, 1, '每次滚动等待（秒）',
                       'dl_scroll_delay',  1,   10,   2, inc=0.5)

    def _dl_toggle(self):
        pass   # no widget enable/disable needed now

    def _on_stop_collect(self):
        """Called when user clicks '停止收集并开始下载' in manual mode."""
        if self._stop_collect_event:
            self._stop_collect_event.set()
        self._stop_collect_btn.configure(state='disabled', text='已停止收集，下载中...')

    # ── Rename tab ─────────────────────────────────
    def _build_rn(self):
        f   = self._trn
        pad = dict(padx=12, pady=7)

        bs = ttk.LabelFrame(f, text='  基本设置')
        bs.pack(fill='x', padx=12, pady=(10,4))
        bs.columnconfigure(1, weight=1)
        self._entry_row(bs, 0, 'X 用户名（不含 @）', 'rn_user')
        self._entry_row(bs, 1, '本地图片文件夹',      'rn_dir', browse=True)

        # FIX #2: same RENAME_OPTS including 【】 format
        rf = ttk.LabelFrame(f, text='  重命名格式')
        rf.pack(fill='x', padx=12, pady=4)
        self.rn_rename_fmt = tk.StringVar(value='【{display_name}】')
        for i,(v,l) in enumerate(RENAME_OPTS):
            ttk.Radiobutton(rf, text=l, variable=self.rn_rename_fmt, value=v
                            ).grid(row=i//3, column=i%3, sticky='w', padx=10, pady=4)

        ol = ttk.LabelFrame(f, text='  运行选项')
        ol.pack(fill='x', padx=12, pady=4)
        self.rn_dry = tk.BooleanVar(value=True)
        ttk.Checkbutton(ol,
                        text='预览模式（完成后弹出预览窗口，可逐张选择是否应用）',
                        variable=self.rn_dry).grid(row=0,column=0,sticky='w',**pad)

        av = ttk.LabelFrame(f, text='  高级设置')
        av.pack(fill='x', padx=12, pady=4)
        self._spin_row(av, 0, '爬取滚动次数',                   'rn_scroll_times', 5,  200, 30)
        self._spin_row(av, 1, '每次滚动等待（秒）',             'rn_scroll_delay', 1,   10,  3, inc=0.5)
        self._spin_row(av, 2, 'pHash 相似度阈值（越小越严格）', 'rn_threshold',    1,   30, 10)

    # ── Widget helpers ─────────────────────────────
    def _entry_row(self, p, row, lbl, attr, browse=False):
        tk.Label(p, text=lbl, bg=BG2, fg=TEXT2, font=F
                 ).grid(row=row, column=0, sticky='w', padx=12, pady=7)
        var = tk.StringVar(); setattr(self, attr, var)
        ttk.Entry(p, textvariable=var).grid(row=row, column=1, sticky='ew', padx=6, pady=7)
        if browse:
            tk.Button(p, text=' 浏览… ', bg=BG3, fg=TEXT, relief='flat',
                      font=FS, cursor='hand2', bd=0,
                      activebackground=ACCENT2, activeforeground='white',
                      command=lambda v=var: v.set(filedialog.askdirectory() or v.get())
                      ).grid(row=row, column=2, padx=(0,12), pady=7)

    def _spin_row(self, p, row, lbl, attr, fr, to, default, inc=1):
        tk.Label(p, text=lbl, bg=BG2, fg=TEXT2, font=F
                 ).grid(row=row, column=0, sticky='w', padx=12, pady=7)
        var = tk.StringVar(value=str(default)); setattr(self, attr, var)
        ttk.Spinbox(p, from_=fr, to=to, increment=inc, textvariable=var, width=9
                    ).grid(row=row, column=1, sticky='w', padx=6, pady=7)

    # ── Config load / save ─────────────────────────
    def _load_cfg_into_ui(self):
        c = self._cfg
        self.dl_user.set(c.get('dl_user', ''))
        self.dl_dir.set(c.get('dl_dir', ''))
        self.dl_mode.set(c.get('dl_filter_mode', 'count'))
        self.dl_count.set(c.get('dl_count', '20'))
        self.dl_max_scroll.set(c.get('dl_max_scroll', '200'))
        self.dl_scroll_delay.set(c.get('dl_scroll_delay', '2.5'))
        self.dl_rename_fmt.set(c.get('dl_rename_fmt', '【{display_name}】'))
        self._dl_toggle()

        self.rn_user.set(c.get('rn_user', ''))
        self.rn_dir.set(c.get('rn_dir', ''))
        self.rn_scroll_times.set(c.get('rn_scroll_times', '30'))
        self.rn_scroll_delay.set(c.get('rn_scroll_delay', '2.5'))
        self.rn_threshold.set(c.get('rn_threshold', '10'))
        self.rn_dry.set(c.get('rn_dry_run', True))
        self.rn_rename_fmt.set(c.get('rn_rename_fmt', '【{display_name}】'))

    def _save_cfg(self):
        save_config({
            'window_geometry': self.geometry(),
            'dl_user':         self.dl_user.get(),
            'dl_dir':          self.dl_dir.get(),
            'dl_filter_mode':  self.dl_mode.get(),
            'dl_count':        self.dl_count.get(),
            'dl_max_scroll':   self.dl_max_scroll.get(),
            'dl_scroll_delay': self.dl_scroll_delay.get(),
            'dl_rename_fmt':   self.dl_rename_fmt.get(),
            'rn_user':         self.rn_user.get(),
            'rn_dir':          self.rn_dir.get(),
            'rn_scroll_times': self.rn_scroll_times.get(),
            'rn_scroll_delay': self.rn_scroll_delay.get(),
            'rn_threshold':    self.rn_threshold.get(),
            'rn_dry_run':      self.rn_dry.get(),
            'rn_rename_fmt':   self.rn_rename_fmt.get(),
        })

    # ── Edge status & launch  (FIX #6) ────────────
    def _check_edge(self):
        if is_cdp_running():
            self.edge_lbl.configure(text="✅ 已连接", fg=SUCCESS)
        else:
            self.edge_lbl.configure(text="⚠️ 未连接，请先启动", fg=WARNING)
        self.after(3000, self._check_edge)

    def _launch_edge(self):
        if is_cdp_running():
            messagebox.showinfo("Edge 已运行",
                "Edge 调试模式已在运行，可直接点击【开始运行】。")
            return
        self.edge_lbl.configure(text="正在启动...", fg=WARNING)
        ok = launch_edge_debug()
        if ok:
            messagebox.showinfo("Edge 已启动",
                "Edge 正在以调试模式启动。\n\n"
                "请在打开的 Edge 中登录 X，\n"
                "然后回到本程序点击【开始运行】。")
        else:
            messagebox.showerror("启动失败",
                "未能自动启动 Edge。\n\n"
                "请手动在命令行运行：\n\n"
                "msedge.exe --remote-debugging-port=9222 https://x.com/login\n\n"
                "或将「启动edge调试模式.bat」放到程序同目录下再试。")

    # ── Toggle run/stop ────────────────────────────
    def _toggle(self):
        if self._running: self._do_stop()
        else: self._do_run()

    def _do_run(self):
        if not is_cdp_running():
            if messagebox.askyesno("Edge 未连接",
                "未检测到 Edge 调试模式。\n\n是否现在尝试启动？"):
                self._launch_edge()
            return
        tab = self.nb.index(self.nb.select())
        cfg = self._cfg_dl() if tab == 0 else self._cfg_rn()
        if cfg is None: return
        self._save_cfg()   # auto-save on run

        w = XWorker(self._q)
        self._worker  = w
        self._running = True
        self.prog['value'] = 0
        self.action_btn.configure(text='■   停止运行', style='Stop.TButton')
        self._ind_frame.pack(side='left', padx=18)
        self._animate_dot()
        fn = w.run_download if tab == 0 else w.run_rename
        threading.Thread(target=fn, args=(cfg,), daemon=True).start()

    def _do_stop(self):
        # FIX #5: set flag AND update UI immediately
        if self._worker:
            self._worker.stop()
        self.log_box.insert('end', '\n⚠️  正在停止，请稍候...\n', 'warn')
        self.log_box.see('end')
        self.action_btn.configure(state='disabled', text='正在停止...')

    def _set_idle(self):
        self._running = False
        self.action_btn.configure(text='▶   开始运行',
                                  style='Run.TButton', state='normal')
        self._ind_frame.pack_forget()

    def _animate_dot(self):
        if not self._running:
            self._dot_cv.itemconfig(self._dot, fill=BG); return
        cols = [WARNING, "#e6b800", WARNING, "#cc9900"]
        self._dot_cv.itemconfig(self._dot, fill=cols[self._dot_idx % 4])
        self._dot_idx += 1
        self.after(400, self._animate_dot)

    def _show_stop_collect(self):
        """Show the '停止收集' banner inside the download tab."""
        self._stop_collect_btn.configure(state='normal', text='⏹  停止收集并开始下载')
        self._stop_collect_bar.pack(fill='x', padx=12, pady=(0,4))
        self.nb.select(self._tdl)   # ensure download tab is visible

    def _hide_stop_collect(self):
        self._stop_collect_bar.pack_forget()
        self._stop_collect_event = None
        win = tk.Toplevel(self)
        win.title("确认 Edge 已登录")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set(); win.focus_force()
        self.update_idletasks()
        mx = self.winfo_x() + self.winfo_width()  // 2
        my = self.winfo_y() + self.winfo_height() // 2
        win.geometry(f"420x200+{mx-210}+{my-100}")
        tk.Label(win, text="🔐  确认 Edge 已登录 X",
                 font=FB, bg=BG, fg=ACCENT).pack(pady=(24,8))
        tk.Label(win,
                 text="请确认你的 Edge 浏览器已登录 X 账号，\n然后点击下方按钮继续。",
                 font=F, bg=BG, fg=TEXT, justify='center').pack(pady=4)
        def _ok(): ready_event.set(); win.destroy()
        tk.Button(win, text='✅  已确认，继续运行',
                  bg=SUCCESS, fg='white', font=FB, relief='flat',
                  cursor='hand2', bd=0, padx=20, pady=10,
                  activebackground='#009e68', activeforeground='white',
                  command=_ok).pack(pady=18)

    # ── Config collectors ──────────────────────────
    def _cfg_dl(self):
        u = self.dl_user.get().strip().lstrip('@')
        d = self.dl_dir.get().strip()
        if not u: messagebox.showwarning('缺少设置','请填写 X 用户名'); return None
        if not d: messagebox.showwarning('缺少设置','请选择保存文件夹'); return None
        mode = self.dl_mode.get()
        cfg = {'username': u, 'save_dir': d,
               'filter_mode':  mode,
               'max_scroll':   int(self.dl_max_scroll.get()),
               'scroll_delay': float(self.dl_scroll_delay.get()),
               'rename_fmt':   self.dl_rename_fmt.get()}
        if mode == 'count':
            cfg['count_limit'] = int(self.dl_count.get())
        elif mode == 'manual':
            # Create a fresh Event; store ref so GUI button can set it
            ev = threading.Event()
            self._stop_collect_event = ev
            cfg['stop_collect_event'] = ev
        return cfg

    def _cfg_rn(self):
        u = self.rn_user.get().strip().lstrip('@')
        d = self.rn_dir.get().strip()
        if not u: messagebox.showwarning('缺少设置','请填写 X 用户名'); return None
        if not d or not Path(d).is_dir():
            messagebox.showwarning('缺少设置','请选择有效的本地图片文件夹'); return None
        return {'username':u,'local_dir':d,
                'scroll_times':   int(self.rn_scroll_times.get()),
                'scroll_delay':   float(self.rn_scroll_delay.get()),
                'hash_threshold': int(self.rn_threshold.get()),
                'dry_run':        self.rn_dry.get(),
                'rename_fmt':     self.rn_rename_fmt.get()}

    # ── Queue poll ─────────────────────────────────
    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                if msg[0] == 'log':
                    self.log_box.insert('end', msg[1]+'\n', msg[2])
                    self.log_box.see('end')
                elif msg[0] == 'progress':
                    if msg[2]: self.prog['maximum'] = msg[2]
                    self.prog['value'] = msg[1]
                elif msg[0] == 'status':
                    self.status_lbl.configure(text=msg[1])
                elif msg[0] == 'ask_ready':
                    self._show_login_dialog(msg[1])
                elif msg[0] == 'show_stop_collect':
                    self._show_stop_collect()
                elif msg[0] == 'hide_stop_collect':
                    self._hide_stop_collect()
                elif msg[0] == 'preview':
                    self._set_idle()
                    self.status_lbl.configure(text="预览就绪")
                    PreviewWindow(self, msg[1])
                elif msg[0] == 'done':
                    self._set_idle()
                    self.status_lbl.configure(
                        text="✅  完成" if msg[1] else "❌  出错，见日志")
        except queue.Empty:
            pass
        self.after(100, self._poll)


# ══════════════════════════════════════════════════════
def main():
    miss = []
    if not PLAYWRIGHT_AVAILABLE: miss.append("playwright")
    if not PIL_AVAILABLE:        miss.append("imagehash Pillow")
    if miss:
        r = tk.Tk(); r.withdraw()
        messagebox.showerror("缺少依赖",
            f"请先运行：\npip install {' '.join(miss)}\n\n"
            "以及：\nplaywright install chromium")
        r.destroy(); return
    XToolApp().mainloop()

if __name__ == '__main__':
    main()
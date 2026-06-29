"""
X Tool  v5  — Python GUI + Edge CDP
修复：1)配置持久化  2)【】格式  3)下载重命名选项  4)预览窗口  5)停止修复  6)Edge启动修复
新增：模式三 — 自动分类（v5.1）
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
import threading, re, requests, hashlib, time, queue, subprocess, os, json, shutil
from pathlib import Path
from datetime import datetime
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
    "window_geometry": "",
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
    # 模式三：自动分类
    "cat_rules":      [],   # [{"target": str, "keywords": [str, ...]}, ...]
    "cat_lib_dir":    "",
    "cat_work_dir":   "",
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
    if BAT_FILE.exists():
        try:
            subprocess.Popen(
                ['cmd', '/c', str(BAT_FILE)],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            return True
        except Exception:
            pass
    edge = find_edge()
    if not edge:
        return False
    try:
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
#  分类规则解析工具函数
# ══════════════════════════════════════════════════════

# 匹配 【...】 或 [...] 包裹的文件夹名，提取内部文字
_CAT_BRACKET_RE = re.compile(r'^[【\[](.+?)[】\]]$')
# 匹配 CJK/非 ASCII 字符块，用于拆分中英混合关键词
_CAT_CJK_RE = re.compile(r'[^\x00-\x7F]+')

def extract_keywords_from_dirname(dirname: str) -> list[str]:
    """
    从分类库文件夹名中自动提取关键词列表。
    规则：去掉首尾【】或[]，按 - 分割，过滤空段。
    对中英混合词（如 yuuhui玉汇）额外提取纯 ASCII 部分作为补充关键词，
    确保 'yuuhui-妲己' 这类只含英文部分的文件夹名也能被命中。
    例：
      【幼愛youmeko-yume chuu-kawayami】 → ['幼愛youmeko','yume chuu','kawayami','youmeko']
      【Kokuhui--yuuhui玉汇】           → ['Kokuhui','yuuhui玉汇','yuuhui']
      Yume Chuu                          → ['Yume Chuu']
    """
    m = _CAT_BRACKET_RE.match(dirname.strip())
    inner = m.group(1) if m else dirname.strip()
    parts = [p.strip() for p in inner.split('-') if p.strip()]
    base = parts if parts else [dirname.strip()]

    # 对中英混合关键词，额外拆出纯 ASCII 段（≥2 字符）作为补充
    extra = []
    for kw in base:
        ascii_only = _CAT_CJK_RE.sub('', kw).strip()
        if ascii_only and ascii_only != kw and len(ascii_only) >= 2:
            extra.append(ascii_only)

    # 去重保序
    seen, result = set(), []
    for k in base + extra:
        if k not in seen:
            seen.add(k); result.append(k)
    return result


def match_rule(folder_name: str, rules: list) -> dict | None:
    """
    对一个文件夹名按顺序匹配规则列表，返回第一个命中的规则 dict，
    未命中返回 None。匹配为大小写不敏感子串匹配。
    """
    name_lower = folder_name.lower()
    for rule in rules:
        for kw in rule.get("keywords", []):
            if kw.strip() and kw.strip().lower() in name_lower:
                return rule
    return None


# ══════════════════════════════════════════════════════
#  Worker  (background thread)
# ══════════════════════════════════════════════════════
class XWorker:
    def __init__(self, q: queue.Queue):
        self.q      = q
        self._stop  = False

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
        mode         = cfg['filter_mode']
        count_limit  = cfg.get('count_limit', 20)
        scroll_delay = cfg.get('scroll_delay', 2.5)
        max_scroll   = cfg.get('max_scroll', 500)
        rename_fmt   = cfg.get('rename_fmt', '【{display_name}】')
        stop_collect = cfg.get('stop_collect_event')

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
        failed   = []

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

        if failed and not self._stop:
            self.log(f"\n🔄  开始重试 {len(failed)} 个失败项...\n", "warn")
            still_failed = []
            self.progress(0, len(failed))
            for i, entry in enumerate(failed):
                if self._stop: break
                item = entry['item']
                stem = entry['stem']
                dest = save_dir / stem
                try:
                    time.sleep(1)
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
#  Preview Window  (Mode 2)
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

        parent.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        self.geometry(f"820x620+{px-410}+{py-310}")

        self._items   = items
        self._vars    = []
        self._parent  = parent

        self._build(items)

    def _build(self, items):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=16, pady=(14,4))
        tk.Label(hdr, text="重命名预览", font=FHEAD, bg=BG, fg=ACCENT).pack(side='left')
        n_matched = sum(1 for i in items if i['matched'])
        tk.Label(hdr, text=f"  {n_matched}/{len(items)} 张匹配",
                 font=F, bg=BG, fg=TEXT2).pack(side='left')

        ttk.Separator(self).pack(fill='x', padx=16, pady=(2,0))

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
                           selectcolor=ACCENT,
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
        self.title("X Tool  v5  ·  图片下载 & 重命名 & 自动分类")
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
        # 分类模块专用 Treeview 样式
        s.configure('Cat.Treeview',
                    background=BG3, foreground=TEXT, fieldbackground=BG3,
                    rowheight=28, font=FM, relief='flat', borderwidth=0)
        s.configure('Cat.Treeview.Heading',
                    background=BG2, foreground=ACCENT, font=FB, relief='flat')
        s.map('Cat.Treeview',
              background=[('selected', ACCENT2)],
              foreground=[('selected', '#ffffff')])

    # ── main UI ────────────────────────────────────
    def _ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=24, pady=(14,4))
        tk.Label(hdr, text="✦ X Tool", font=FHEAD, bg=BG, fg=ACCENT).pack(side='left')
        tk.Label(hdr, text="  图片下载 & 重命名 & 自动分类  ·  Edge 版",
                 font=F, bg=BG, fg=TEXT2).pack(side='left')
        ttk.Separator(self).pack(fill='x', padx=24, pady=(2,0))

        # Edge status bar
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

        # Notebook — 三个 Tab
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='x', padx=24, pady=(8,0))
        self._tdl = ttk.Frame(self.nb)
        self._trn = ttk.Frame(self.nb)
        self._tcat = tk.Frame(self.nb, bg=BG)   # 模式三：自动分类
        self.nb.add(self._tdl,  text='  ↓  模式一：从 Likes 下载原图  ')
        self.nb.add(self._trn,  text='  ✎  模式二：本地图片重命名  ')
        self.nb.add(self._tcat, text='  🗂  模式三：自动分类  ')
        self._build_dl()
        self._build_rn()
        self._build_cat()

        ttk.Separator(self).pack(fill='x', padx=24, pady=(8,0))

        # Log（模式一二共用）
        log_lf = ttk.LabelFrame(self, text='  运行日志（模式一 / 二）')
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

        self._stop_collect_bar = tk.Frame(f, bg="#1a2a1a", relief='flat')
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
        self._stop_collect_event = None

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
        pass

    def _on_stop_collect(self):
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

    # ══════════════════════════════════════════════
    #  模式三：自动分类 Tab
    # ══════════════════════════════════════════════
    def _build_cat(self):
        f = self._tcat
        f.columnconfigure(0, weight=1)

        # ── 区域 A：规则管理 ──────────────────────
        sec_a = tk.LabelFrame(f, text='  规则管理',
                              bg=BG, fg=ACCENT, font=FB,
                              relief='flat', bd=1,
                              highlightbackground=BORDER, highlightthickness=1)
        sec_a.pack(fill='x', padx=12, pady=(10,4))
        sec_a.columnconfigure(1, weight=1)

        # 扫描分类库行
        tk.Label(sec_a, text='分类库目录', bg=BG, fg=TEXT2, font=FS,
                 width=12, anchor='w').grid(row=0, column=0, sticky='w', padx=(12,6), pady=6)
        self.cat_lib_dir = tk.StringVar()
        lib_ef = tk.Frame(sec_a, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        lib_ef.grid(row=0, column=1, sticky='ew', padx=(0,6), pady=6)
        tk.Entry(lib_ef, textvariable=self.cat_lib_dir, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=F, bd=5).pack(fill='x')
        tk.Button(sec_a, text='浏览', bg=BG3, fg=TEXT, relief='flat', font=FS,
                  cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground=ACCENT2, activeforeground='white',
                  command=lambda: self.cat_lib_dir.set(
                      filedialog.askdirectory() or self.cat_lib_dir.get())
                  ).grid(row=0, column=2, padx=(0,6), pady=6)
        tk.Button(sec_a, text='🔍 扫描提取规则', bg=ACCENT, fg='white',
                  relief='flat', font=FB, cursor='hand2', bd=0, padx=12, pady=5,
                  activebackground=ACCENT2, activeforeground='white',
                  command=self._cat_scan_lib
                  ).grid(row=0, column=3, padx=(0,12), pady=6)

        tk.Label(sec_a,
                 text='扫描后自动提取分类关键词，也可手动添加规则。双击列表行可快速编辑。',
                 bg=BG, fg=TEXT2, font=('Segoe UI', 8)
                 ).grid(row=1, column=0, columnspan=4, sticky='w', padx=12, pady=(0,6))

        # 规则列表 Treeview
        tv_frame = tk.Frame(sec_a, bg=BORDER, padx=1, pady=1)
        tv_frame.grid(row=2, column=0, columnspan=4, sticky='ew', padx=12, pady=(0,6))
        tv_frame.columnconfigure(0, weight=1)

        self.cat_tree = ttk.Treeview(
            tv_frame,
            columns=('target', 'keywords'),
            show='headings',
            height=6,
            style='Cat.Treeview',
            selectmode='browse',
        )
        self.cat_tree.heading('target',   text='目标文件夹名')
        self.cat_tree.heading('keywords', text='匹配关键词（逗号分隔，大小写不敏感）')
        self.cat_tree.column('target',   width=220, minwidth=160, anchor='w')
        self.cat_tree.column('keywords', width=500, minwidth=200, anchor='w')

        vsb_cat = ttk.Scrollbar(tv_frame, orient='vertical', command=self.cat_tree.yview)
        self.cat_tree.configure(yscrollcommand=vsb_cat.set)
        self.cat_tree.grid(row=0, column=0, sticky='ew')
        vsb_cat.grid(row=0, column=1, sticky='ns')

        self.cat_tree.bind('<<TreeviewSelect>>', self._cat_on_select)
        self.cat_tree.bind('<Double-1>', self._cat_on_double_click)

        # 规则列表操作按钮行
        list_btn_row = tk.Frame(sec_a, bg=BG)
        list_btn_row.grid(row=3, column=0, columnspan=4, sticky='w', padx=12, pady=(0,8))
        tk.Button(list_btn_row, text='＋ 新增规则', bg=BG3, fg=TEXT,
                  relief='flat', font=FS, cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground=ACCENT2, activeforeground='white',
                  command=self._cat_add_rule
                  ).pack(side='left', padx=(0,4))
        tk.Button(list_btn_row, text='✕ 删除选中', bg='#2e1e1e', fg=ERROR,
                  relief='flat', font=FS, cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground='#3d2020', activeforeground=ERROR,
                  command=self._cat_delete_rule
                  ).pack(side='left', padx=(0,4))
        tk.Button(list_btn_row, text='↑ 上移', bg=BG3, fg=TEXT2,
                  relief='flat', font=FS, cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground=BG2, activeforeground=TEXT,
                  command=lambda: self._cat_move_rule(-1)
                  ).pack(side='left', padx=(0,4))
        tk.Button(list_btn_row, text='↓ 下移', bg=BG3, fg=TEXT2,
                  relief='flat', font=FS, cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground=BG2, activeforeground=TEXT,
                  command=lambda: self._cat_move_rule(1)
                  ).pack(side='left', padx=(0,4))
        tk.Button(list_btn_row, text='💾 保存规则', bg='#1e3a1e', fg=SUCCESS,
                  relief='flat', font=FS, cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground='#1a501a', activeforeground=SUCCESS,
                  command=self._cat_save_rules_to_cfg
                  ).pack(side='right')

        # 编辑区（选中后填充，保存写回）
        edit_frame = tk.Frame(sec_a, bg=BG2,
                              highlightbackground=BORDER, highlightthickness=1)
        edit_frame.grid(row=4, column=0, columnspan=4, sticky='ew', padx=12, pady=(0,10))
        edit_frame.columnconfigure(1, weight=1)
        edit_frame.columnconfigure(3, weight=2)

        tk.Label(edit_frame, text='目标文件夹名', bg=BG2, fg=TEXT2, font=FS,
                 width=12, anchor='w').grid(row=0, column=0, sticky='w', padx=(10,6), pady=8)
        self.cat_edit_target = tk.StringVar()
        target_ef = tk.Frame(edit_frame, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        target_ef.grid(row=0, column=1, sticky='ew', padx=(0,16), pady=8)
        tk.Entry(target_ef, textvariable=self.cat_edit_target, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=F, bd=5).pack(fill='x')

        tk.Label(edit_frame, text='匹配关键词', bg=BG2, fg=TEXT2, font=FS,
                 width=10, anchor='w').grid(row=0, column=2, sticky='w', padx=(0,6), pady=8)
        self.cat_edit_keywords = tk.StringVar()
        kw_ef = tk.Frame(edit_frame, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        kw_ef.grid(row=0, column=3, sticky='ew', padx=(0,6), pady=8)
        tk.Entry(kw_ef, textvariable=self.cat_edit_keywords, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=F, bd=5).pack(fill='x')

        tk.Button(edit_frame, text='✔ 保存修改', bg=ACCENT, fg='white',
                  relief='flat', font=FS, cursor='hand2', bd=0, padx=12, pady=6,
                  activebackground=ACCENT2, activeforeground='white',
                  command=self._cat_apply_edit
                  ).grid(row=0, column=4, padx=(6,10), pady=8)

        tk.Label(edit_frame,
                 text='提示：多个关键词用逗号分隔，匹配顺序从上至下，命中第一条即停止',
                 bg=BG2, fg=TEXT2, font=('Segoe UI', 8)
                 ).grid(row=1, column=0, columnspan=5, sticky='w', padx=10, pady=(0,6))

        # ── 区域 B：执行区 ────────────────────────
        sec_b = tk.LabelFrame(f, text='  执行分类',
                              bg=BG, fg=ACCENT, font=FB,
                              relief='flat', bd=1,
                              highlightbackground=BORDER, highlightthickness=1)
        sec_b.pack(fill='x', padx=12, pady=(4,4))
        sec_b.columnconfigure(1, weight=1)

        tk.Label(sec_b, text='待分类目录', bg=BG, fg=TEXT2, font=FS,
                 width=12, anchor='w').grid(row=0, column=0, sticky='w', padx=(12,6), pady=8)
        self.cat_work_dir = tk.StringVar()
        work_ef = tk.Frame(sec_b, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
        work_ef.grid(row=0, column=1, sticky='ew', padx=(0,6), pady=8)
        tk.Entry(work_ef, textvariable=self.cat_work_dir, bg=BG3, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=F, bd=5).pack(fill='x')
        tk.Button(sec_b, text='浏览', bg=BG3, fg=TEXT, relief='flat', font=FS,
                  cursor='hand2', bd=0, padx=10, pady=5,
                  activebackground=ACCENT2, activeforeground='white',
                  command=lambda: self.cat_work_dir.set(
                      filedialog.askdirectory() or self.cat_work_dir.get())
                  ).grid(row=0, column=2, padx=(0,6), pady=8)

        tk.Label(sec_b,
                 text='将该目录下的所有直接子文件夹按上方规则分类移动。未命中规则的文件夹放入【其他】。',
                 bg=BG, fg=TEXT2, font=('Segoe UI', 8)
                 ).grid(row=1, column=0, columnspan=3, sticky='w', padx=12, pady=(0,4))

        exec_btn_row = tk.Frame(sec_b, bg=BG)
        exec_btn_row.grid(row=2, column=0, columnspan=3, sticky='w', padx=12, pady=(4,10))
        tk.Button(exec_btn_row, text='🔍 预览分类结果', bg="#0d3060", fg="#79C0FF",
                  relief='flat', font=FB, cursor='hand2', bd=0, padx=14, pady=7,
                  activebackground="#1056aa", activeforeground='#79C0FF',
                  command=self._cat_preview
                  ).pack(side='left', padx=(0,8))
        self.cat_exec_btn = tk.Button(
            exec_btn_row, text='▶ 执行分类', bg='#1e3a1e', fg=SUCCESS,
            relief='flat', font=FB, cursor='hand2', bd=0, padx=14, pady=7,
            activebackground='#1a501a', activeforeground=SUCCESS,
            state='disabled',
            command=self._cat_execute
        )
        self.cat_exec_btn.pack(side='left')

        # ── 区域 C：分类日志 ──────────────────────
        log_lf_cat = tk.LabelFrame(f, text='  分类日志',
                                   bg=BG, fg=ACCENT, font=FB,
                                   relief='flat', bd=1,
                                   highlightbackground=BORDER, highlightthickness=1)
        log_lf_cat.pack(fill='both', expand=True, padx=12, pady=(4,8))
        log_lf_cat.rowconfigure(0, weight=1)
        log_lf_cat.columnconfigure(0, weight=1)

        log_btn_row = tk.Frame(log_lf_cat, bg=BG)
        log_btn_row.pack(fill='x', padx=6, pady=(4,2))
        self.cat_log_status = tk.Label(log_btn_row, text='─ 就绪 ─',
                                       bg=BG, fg=TEXT2, font=FS)
        self.cat_log_status.pack(side='left')
        tk.Button(log_btn_row, text='清空', bg=BG3, fg=TEXT2, relief='flat',
                  font=FS, cursor='hand2', bd=0, padx=8, pady=3,
                  activebackground=BG2, activeforeground=TEXT,
                  command=self._cat_log_clear
                  ).pack(side='right')

        self.cat_log = tk.Text(
            log_lf_cat, bg=BG3, fg=TEXT, font=FM,
            bd=0, relief='flat', state='disabled',
            highlightthickness=0, wrap='none', height=10,
        )
        cat_vsb = ttk.Scrollbar(log_lf_cat, orient='vertical', command=self.cat_log.yview)
        cat_hsb = ttk.Scrollbar(log_lf_cat, orient='horizontal', command=self.cat_log.xview)
        self.cat_log.configure(yscrollcommand=cat_vsb.set, xscrollcommand=cat_hsb.set)
        self.cat_log.pack(side='left', fill='both', expand=True, padx=(6,0), pady=(0,6))
        cat_vsb.pack(side='right', fill='y', pady=(0,6))

        for tag, col in [('ok', SUCCESS), ('warn', WARNING), ('err', ERROR),
                         ('info', ACCENT), ('dim', TEXT2)]:
            self.cat_log.tag_config(tag, foreground=col)

        # 内部状态
        self._cat_rules_data  = []   # [{"target": str, "keywords": [str]}, ...]
        self._cat_preview_data = []  # [{"src": Path, "dst_dir": str, "rule_target": str}, ...]
        self._cat_edit_iid    = None # 当前编辑行的 Treeview iid

    # ── 分类：日志写入 ─────────────────────────────
    def _cat_log_write(self, msg: str, tag: str = 'info'):
        ts = time.strftime('%H:%M:%S')
        self.cat_log.configure(state='normal')
        self.cat_log.insert('end', f'[{ts}] {msg}\n', tag)
        self.cat_log.see('end')
        self.cat_log.configure(state='disabled')

    def _cat_log_clear(self):
        self.cat_log.configure(state='normal')
        self.cat_log.delete('1.0', 'end')
        self.cat_log.configure(state='disabled')
        self.cat_log_status.configure(text='─ 就绪 ─', fg=TEXT2)

    # ── 分类：Treeview 刷新 ────────────────────────
    def _cat_refresh_tree(self):
        """将 self._cat_rules_data 全量刷新到 Treeview。"""
        for iid in self.cat_tree.get_children():
            self.cat_tree.delete(iid)
        for rule in self._cat_rules_data:
            kw_str = ', '.join(rule.get('keywords', []))
            self.cat_tree.insert('', 'end',
                                 values=(rule['target'], kw_str))

    # ── 分类：扫描分类库目录 ───────────────────────
    def _cat_scan_lib(self):
        d = self.cat_lib_dir.get().strip()
        if not d or not Path(d).is_dir():
            messagebox.showwarning('提示', '请先选择有效的分类库目录')
            return
        lib = Path(d)
        subdirs = [p.name for p in lib.iterdir() if p.is_dir()]
        if not subdirs:
            messagebox.showinfo('提示', '该目录下没有找到子文件夹')
            return

        # 提取规则（已有规则保留，不重复添加）
        existing_targets = {r['target'] for r in self._cat_rules_data}
        added = 0
        for dname in sorted(subdirs):
            if dname in existing_targets:
                continue
            kws = extract_keywords_from_dirname(dname)
            self._cat_rules_data.append({'target': dname, 'keywords': kws})
            added += 1

        self._cat_refresh_tree()
        self._cat_log_write(
            f'扫描完成：读取到 {len(subdirs)} 个文件夹，新增 {added} 条规则', 'ok')
        if added == 0:
            self._cat_log_write('所有文件夹已在规则列表中，无新增', 'dim')

    # ── 分类：选中行事件 ───────────────────────────
    def _cat_on_select(self, _event=None):
        sel = self.cat_tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self.cat_tree.item(iid, 'values')
        self.cat_edit_target.set(vals[0] if vals else '')
        self.cat_edit_keywords.set(vals[1] if len(vals) > 1 else '')
        self._cat_edit_iid = iid

    def _cat_on_double_click(self, _event=None):
        """双击等同于选中后直接聚焦到关键词输入框。"""
        self._cat_on_select()

    # ── 分类：应用编辑 ─────────────────────────────
    def _cat_apply_edit(self):
        iid = self._cat_edit_iid
        if not iid or iid not in self.cat_tree.get_children():
            messagebox.showinfo('提示', '请先在列表中选中一行')
            return
        new_target = self.cat_edit_target.get().strip()
        new_kw_raw = self.cat_edit_keywords.get()
        if not new_target:
            messagebox.showwarning('提示', '目标文件夹名不能为空')
            return
        new_keywords = [k.strip() for k in new_kw_raw.split(',') if k.strip()]

        # 找到对应数据行并更新
        idx = self.cat_tree.get_children().index(iid)
        self._cat_rules_data[idx]['target']   = new_target
        self._cat_rules_data[idx]['keywords'] = new_keywords
        self._cat_refresh_tree()
        # 重新选中该行
        children = self.cat_tree.get_children()
        if idx < len(children):
            self.cat_tree.selection_set(children[idx])
            self._cat_edit_iid = children[idx]
        self._cat_log_write(f'规则已更新：{new_target}  →  {", ".join(new_keywords)}', 'ok')

    # ── 分类：新增规则 ─────────────────────────────
    def _cat_add_rule(self):
        self._cat_rules_data.append({'target': '新规则', 'keywords': []})
        self._cat_refresh_tree()
        # 选中新行并填入编辑区
        children = self.cat_tree.get_children()
        if children:
            last = children[-1]
            self.cat_tree.selection_set(last)
            self.cat_tree.see(last)
            self._cat_edit_iid = last
            self.cat_edit_target.set('新规则')
            self.cat_edit_keywords.set('')

    # ── 分类：删除规则 ─────────────────────────────
    def _cat_delete_rule(self):
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo('提示', '请先选中要删除的规则')
            return
        iid = sel[0]
        idx = list(self.cat_tree.get_children()).index(iid)
        target = self._cat_rules_data[idx]['target']
        if not messagebox.askyesno('确认', f'删除规则「{target}」？'):
            return
        del self._cat_rules_data[idx]
        self._cat_refresh_tree()
        self._cat_edit_iid = None
        self.cat_edit_target.set('')
        self.cat_edit_keywords.set('')
        self._cat_log_write(f'已删除规则：{target}', 'warn')

    # ── 分类：移动规则顺序 ─────────────────────────
    def _cat_move_rule(self, direction: int):
        """direction: -1 上移, +1 下移"""
        sel = self.cat_tree.selection()
        if not sel:
            return
        iid = sel[0]
        children = list(self.cat_tree.get_children())
        idx = children.index(iid)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._cat_rules_data):
            return
        self._cat_rules_data[idx], self._cat_rules_data[new_idx] = \
            self._cat_rules_data[new_idx], self._cat_rules_data[idx]
        self._cat_refresh_tree()
        new_children = self.cat_tree.get_children()
        if new_idx < len(new_children):
            self.cat_tree.selection_set(new_children[new_idx])
            self.cat_tree.see(new_children[new_idx])
            self._cat_edit_iid = new_children[new_idx]

    # ── 分类：保存规则到配置 ───────────────────────
    def _cat_save_rules_to_cfg(self):
        self._save_cfg()
        self._cat_log_write(
            f'已保存 {len(self._cat_rules_data)} 条规则到配置文件', 'ok')

    # ── 分类：预览 ────────────────────────────────
    def _cat_preview(self):
        work = self.cat_work_dir.get().strip()
        if not work or not Path(work).is_dir():
            messagebox.showwarning('提示', '请先选择有效的待分类目录')
            return
        if not self._cat_rules_data:
            messagebox.showwarning('提示', '规则列表为空，请先添加规则或扫描分类库')
            return

        work_path = Path(work)
        # 收集直接子文件夹，排除已是目标文件夹名的（避免把目标文件夹自身移进去）
        target_names = {r['target'] for r in self._cat_rules_data} | {'【其他】'}
        subdirs = [
            p for p in work_path.iterdir()
            if p.is_dir() and p.name not in target_names
        ]

        if not subdirs:
            messagebox.showinfo('提示', '待分类目录下没有可分类的子文件夹（目标文件夹名已自动排除）')
            return

        self._cat_preview_data = []
        self._cat_log_clear()
        self._cat_log_write(f'预览：共 {len(subdirs)} 个文件夹待分类', 'info')
        self._cat_log_write('─' * 60, 'dim')

        matched_count  = 0
        other_count    = 0
        for p in sorted(subdirs, key=lambda x: x.name):
            rule = match_rule(p.name, self._cat_rules_data)
            if rule:
                target = rule['target']
                matched_count += 1
                tag = 'ok'
            else:
                target = '【其他】'
                other_count += 1
                tag = 'dim'

            dst_dir = work_path / target
            conflict = (dst_dir / p.name).exists()
            self._cat_preview_data.append({
                'src':         p,
                'dst_dir':     dst_dir,
                'rule_target': target,
                'conflict':    conflict,
            })
            conflict_hint = '  ⚠ 目标已存在，将跳过' if conflict else ''
            self._cat_log_write(
                f'  {p.name}  →  {target}{conflict_hint}',
                'warn' if conflict else tag
            )

        self._cat_log_write('─' * 60, 'dim')
        self._cat_log_write(
            f'预览完成：命中规则 {matched_count} 个，归入【其他】{other_count} 个',
            'info'
        )
        conflicts = sum(1 for d in self._cat_preview_data if d['conflict'])
        if conflicts:
            self._cat_log_write(f'⚠ 其中 {conflicts} 个存在冲突，执行时将自动跳过', 'warn')

        self.cat_exec_btn.configure(state='normal')
        self.cat_log_status.configure(
            text=f'预览完成：{len(subdirs)} 个文件夹', fg=WARNING)

    # ── 分类：执行 ────────────────────────────────
    def _cat_execute(self):
        if not self._cat_preview_data:
            messagebox.showinfo('提示', '请先执行预览')
            return
        to_move = [d for d in self._cat_preview_data if not d['conflict']]
        skip    = [d for d in self._cat_preview_data if d['conflict']]
        if not messagebox.askyesno(
            '确认执行',
            f'即将移动 {len(to_move)} 个文件夹\n'
            f'跳过冲突 {len(skip)} 个\n\n'
            '此操作不可撤销，是否继续？'
        ):
            return

        self.cat_exec_btn.configure(state='disabled')
        self._cat_log_write('开始执行分类移动…', 'info')

        def worker():
            ok = fail = skipped = 0
            total = len(to_move)
            for i, item in enumerate(to_move):
                src: Path = item['src']
                dst_dir: Path = item['dst_dir']
                try:
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    final_dst = dst_dir / src.name
                    if final_dst.exists():
                        # 再次检查（防止并发或预览后手动新建了同名文件夹）
                        skipped += 1
                        self.after(0, self._cat_log_write,
                                   f'  ⚠ 跳过（目标已存在）: {src.name}', 'warn')
                    else:
                        shutil.move(str(src), str(final_dst))
                        ok += 1
                        self.after(0, self._cat_log_write,
                                   f'  ✓ [{i+1}/{total}] {src.name}  →  {dst_dir.name}', 'ok')
                except Exception as e:
                    fail += 1
                    self.after(0, self._cat_log_write,
                               f'  ✗ 失败: {src.name}  ({e})', 'err')

            # 汇总
            summary = (
                f'执行完成：成功 {ok} 个'
                + (f'  失败 {fail} 个' if fail else '')
                + (f'  跳过 {skipped + len(skip)} 个' if (skipped + len(skip)) else '')
            )
            self.after(0, self._cat_log_write, '─' * 60, 'dim')
            self.after(0, self._cat_log_write, summary, 'ok' if not fail else 'warn')
            self.after(0, self.cat_log_status.configure,
                       {'text': summary, 'fg': SUCCESS if not fail else WARNING})
            self.after(0, self.cat_exec_btn.configure, {'state': 'disabled'})
            # 清空预览数据，防止重复执行
            self._cat_preview_data.clear()

        threading.Thread(target=worker, daemon=True).start()

    # ── Widget helpers ─────────────────────────────
    def _entry_row(self, p, row, lbl, attr, browse=False):
        tk.Label(p, text=lbl, bg=BG2, fg=TEXT2, font=F,
                 width=16, anchor="w").grid(row=row, column=0, sticky='w', padx=12, pady=7)
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

        # 模式三
        self.cat_lib_dir.set(c.get('cat_lib_dir', ''))
        self.cat_work_dir.set(c.get('cat_work_dir', ''))
        self._cat_rules_data = c.get('cat_rules', [])
        self._cat_refresh_tree()

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
            # 模式三
            'cat_lib_dir':     self.cat_lib_dir.get(),
            'cat_work_dir':    self.cat_work_dir.get(),
            'cat_rules':       self._cat_rules_data,
        })

    # ── Edge status & launch ───────────────────────
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
        tab = self.nb.index(self.nb.select())
        if tab == 2:
            # 模式三不走 XWorker，直接提示用预览/执行按钮
            messagebox.showinfo('模式三', '请使用「预览分类结果」和「执行分类」按钮操作。')
            return
        if not is_cdp_running():
            if messagebox.askyesno("Edge 未连接",
                "未检测到 Edge 调试模式。\n\n是否现在尝试启动？"):
                self._launch_edge()
            return
        cfg = self._cfg_dl() if tab == 0 else self._cfg_rn()
        if cfg is None: return
        self._save_cfg()

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
        self._stop_collect_btn.configure(state='normal', text='⏹  停止收集并开始下载')
        self._stop_collect_bar.pack(fill='x', padx=12, pady=(0,4))
        self.nb.select(self._tdl)

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

    def _show_login_dialog(self, ready_event: threading.Event):
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
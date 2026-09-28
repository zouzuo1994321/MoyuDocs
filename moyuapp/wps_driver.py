# -*- coding: utf-8 -*-
"""真实 WPS 驱动器：拉起 WPS 进程，并把预载文本逐字“打”进真实 WPS 窗口。

WPS 个人版未注册 COM 自动化接口（无 wps.Application），因此无法用代码读写文档。
本模块改用 UI 级方案：
  1. 子进程拉起 wps.exe 打开一个空白 docx（跳过开始中心）；
  2. 按进程 PID 定位 WPS 主窗口并置前聚焦文档区；
  3. 字符经 WM_CHAR 直投文档画布（_WwG）绕过键盘与输入法（IME）链路，
     中文逐字输入稳定且不依赖输入法；换行/制表等控制键走 SendInput，
     剪贴板 Ctrl+V 与 SendInput Unicode 作为兜底。

仅依赖 ctypes + 标准库，无需第三方包。
"""

import os
import sys
import glob
import ctypes
import subprocess
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
try:
    imm32 = ctypes.windll.imm32
except AttributeError:
    imm32 = None

# ---- 常量 ----
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_HOME = 0x24
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WM_CHAR = 0x0102

# ---- INPUT 结构体（64 位 Windows 必须为 40 字节！）----
# 注意：Windows 64 位下 INPUT = DWORD(type) + 8 字节对齐填充 + union(28) = 40 字节。
# union 最大成员 MOUSEINPUT 为 28 字节且含指针（8 字节对齐），因此整体 sizeof(INPUT) == 40。
# 若定义成 32 字节，SendInput 会因结构尺寸不符而静默失败（字打不进 WPS）。
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 28)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _GUITHREADINFO(ctypes.Structure):
    """GetGUIThreadInfo 结构体（用于查询 WPS 线程内当前持有键盘焦点的子窗口）。"""
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


# ---- 额外常量（剪贴板兜底 / 前台置顶）----
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56
ASFW_ANY = 0xFFFFFFFF  # AllowSetForegroundWindow 参数：允许任意进程置前

# 显式声明 Win32 函数签名，避免 32/64 位下默认推断出错
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
user32.AllowSetForegroundWindow.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
kernel32.GlobalSize.restype = ctypes.c_size_t
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []

# 输入法状态检测（手动按键模式：IMe 开=放行手动打字，关=吞键驱动摸鱼）
if imm32 is not None:
    imm32.ImmGetContext.argtypes = [wintypes.HWND]
    imm32.ImmGetContext.restype = wintypes.HANDLE
    imm32.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
    imm32.ImmGetOpenStatus.restype = wintypes.BOOL
    imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    imm32.ImmReleaseContext.restype = wintypes.BOOL


def _window_tid(hwnd):
    """返回窗口所属线程 id（GetWindowThreadProcessId 的返回值即线程 id）。"""
    return user32.GetWindowThreadProcessId(hwnd, None)


def current_foreground_image():
    """返回当前前台窗口的进程映像名（小写）；用于诊断。"""
    fg = user32.GetForegroundWindow()
    if not fg:
        return ""
    return _process_image_name(_window_pid(fg))


def _pack_input(vk, scan, flags):
    """返回 KEYBDINPUT 在内存中的 28 字节布局（仅用于单元测试/参考）。"""
    import struct
    b = bytearray(28)
    struct.pack_into("<H", b, 0, vk & 0xFFFF)          # wVk
    struct.pack_into("<H", b, 2, scan & 0xFFFF)        # wScan
    struct.pack_into("<I", b, 4, flags & 0xFFFFFFFF)  # dwFlags
    struct.pack_into("<I", b, 8, 0)                    # time
    struct.pack_into("<Q", b, 12, 0)                   # dwExtraInfo
    return b


def _send_input_list(events):
    """events: list of (vk, scan, flags)。一次性 SendInput 发出（down+up 由调用方成对传入）。"""
    if not events:
        return 0
    arr = (INPUT * len(events))()
    for i, (vk, scan, flags) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki.wVk = vk & 0xFFFF
        arr[i].u.ki.wScan = scan & 0xFFFF
        arr[i].u.ki.dwFlags = flags & 0xFFFFFFFF
        arr[i].u.ki.time = 0
        arr[i].u.ki.dwExtraInfo = None
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    return user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))


# ---- WPS 路径探测 ----
WPS_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Kingsoft\WPS Office"),
    r"C:\Program Files (x86)\Kingsoft\WPS Office",
    r"C:\Program Files\Kingsoft\WPS Office",
]


def find_wps_path():
    """返回 wps.exe 绝对路径，未找到返回 None（优先最高版本号目录）。"""
    for base in WPS_CANDIDATES:
        if not os.path.isdir(base):
            continue
        hits = glob.glob(os.path.join(base, "**", "office6", "wps.exe"), recursive=True)
        if hits:
            def verkey(p):
                return [int(x) if x.isdigit() else 0 for x in p.replace("\\", "/").split("/")]
            hits.sort(key=verkey, reverse=True)
            return hits[0]
    return None


def create_blank_docx(path):
    """生成一个完整、WPS 必能打开的空白 docx（含全部必需部件），进入正文编辑态。"""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p/></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>摸鱼文书</dc:title></cp:coreProperties>'
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        '<Application>摸鱼文书</Application></Properties>'
    )
    import zipfile
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)


# ---- 窗口枚举（按 PID / 按进程映像名）----
WPS_IMAGE_NAMES = ("wps.exe", "et.exe", "wpp.exe", "wpsoffice.exe")


def _process_image_name(pid):
    """返回进程映像名（小写），失败返回空串。"""
    if not pid:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = ctypes.windll.kernel32
    k32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        k32.CloseHandle(h)


def _window_pid(hwnd):
    pid_buf = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
    return pid_buf.value


def _enum_windows_by_pid(pid):
    found = []

    def cb(hwnd, lparam):
        if _window_pid(hwnd) == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def _enum_windows_by_image(names):
    """枚举所有属于指定映像名进程的可见顶层窗口。"""
    names = {n.lower() for n in names}
    found = []

    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd) and _process_image_name(_window_pid(hwnd)) in names:
            found.append(hwnd)
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


class WpsDriver:
    """封装一次 WPS 会话的启动、聚焦、逐字输入与 IME 控制。"""

    def __init__(self):
        self.pid = None
        self.proc = None
        self.hwnd = None
        self._ime_ctx = None  # 保存原 IME 上下文以便还原
        self._type_hwnd = None  # WM_CHAR 直投目标（文档画布子窗口），缓存
        self._type_count = 0  # 已直投次数（定期刷新目标句柄，防画布重建）

    # ---------- 启动 ----------
    def launch(self, blank_doc_path=None, timeout=20):
        """启动 WPS 并打开空白文档，返回是否成功。"""
        exe = find_wps_path()
        if not exe:
            return False, "未找到 wps.exe，请确认已安装 WPS。"
        if blank_doc_path:
            os.makedirs(os.path.dirname(blank_doc_path), exist_ok=True)
            if not os.path.exists(blank_doc_path):
                create_blank_docx(blank_doc_path)
            args = [exe, blank_doc_path]
        else:
            args = [exe]
        self.proc = subprocess.Popen(args)
        self.pid = self.proc.pid
        # 等待主窗口出现。
        # 注意：WPS 是单实例架构，Popen 的进程可能只是把文件转交给已有实例后退出，
        # 因此除按 PID 找窗口外，还要按进程映像名（wps.exe 等）兜底找窗口。
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            hwnd = self._find_window()
            if hwnd:
                self.hwnd = hwnd
                break
            time.sleep(0.1)
        else:
            return False, "WPS 启动后未找到主窗口（可能弹出了登录/开始中心）。"
        self.focus()
        # 注意：不再在启动时禁用 IME。
        # v2.0.5 起“打字”改走 WM_CHAR 直投（不经键盘/IME 链路），IME 是否开启都不影响
        # 自动打字；而保留 IME 可让用户在前台随时用输入法手动补充内容（见 #13）。
        return True, exe

    def _find_window(self):
        """定位 WPS 主窗口：优先本进程 PID，其次按映像名（wps.exe 等）取面积最大者。"""
        wins = _enum_windows_by_pid(self.pid) if self.pid else []
        if not wins:
            wins = _enum_windows_by_image(WPS_IMAGE_NAMES)
        if not wins:
            return None
        return max(wins, key=self._window_area)

    @staticmethod
    def _window_area(hwnd):
        r = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return (r.right - r.left) * (r.bottom - r.top)
        return 0

    # ---------- 聚焦 ----------
    def _ensure_hwnd(self):
        """hwnd 失效（窗口关闭/易主）时重新定位。"""
        if self.hwnd and user32.IsWindow(self.hwnd) and user32.IsWindowVisible(self.hwnd):
            return True
        self.hwnd = self._find_window()
        return bool(self.hwnd)

    def focus(self):
        """把 WPS 主窗口置前，并点击正文区中央以聚焦文档编辑区。

        前台窗口受 Windows ForegroundLockTimeout 限制：后台进程直接
        SetForegroundWindow 常被静默拒绝。这里先 AllowSetForegroundWindow(ANY)，
        再临时 AttachThreadInput 到当前前台线程来“借”其置前权限，成功率更高。
        """
        if not self._ensure_hwnd():
            return False
        user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        try:
            user32.AllowSetForegroundWindow(ASFW_ANY)
        except Exception:
            pass
        fg = user32.GetForegroundWindow()
        if fg:
            fg_tid = _window_tid(fg)
            our_tid = kernel32.GetCurrentThreadId()
            if fg_tid and our_tid and fg_tid != our_tid:
                try:
                    user32.AttachThreadInput(our_tid, fg_tid, True)
                    user32.SetForegroundWindow(self.hwnd)
                    user32.AttachThreadInput(our_tid, fg_tid, False)
                except Exception:
                    try:
                        user32.AttachThreadInput(our_tid, fg_tid, False)
                    except Exception:
                        pass
        # 最后再尝试一次（Attach 失败时兜底）
        user32.SetForegroundWindow(self.hwnd)
        # 点击正文区中央，确保光标落在文档内。
        # 必须用窗口在屏幕上的矩形（GetWindowRect）算屏幕坐标，
        # GetClientRect 是相对客户区的坐标，直接当屏幕坐标会导致点歪。
        r = wintypes.RECT()
        if user32.GetWindowRect(self.hwnd, ctypes.byref(r)):
            cx = (r.left + r.right) // 2
            cy = (r.top + r.bottom) // 2
            user32.SetCursorPos(cx, cy)
            user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        return True

    def is_alive(self):
        """WPS 进程是否还活着（用户手动关闭后 pid 不再有效）。"""
        if not self.pid:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False

    def is_foreground(self):
        """当前前台窗口是否属于 WPS。

        不能只比 PID：WPS 单实例架构下，打开文档的窗口可能属于另一个
        wps.exe 进程（与我们 Popen 的 pid 不同），因此用映像名兜底判定。
        """
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        pid = _window_pid(fg)
        if self.pid and pid == self.pid:
            return True
        return _process_image_name(pid) in WPS_IMAGE_NAMES

    # ---------- IME ----------
    def disable_ime(self):
        """禁用该窗口输入法，保证 Unicode 直插不触发组合输入。"""
        if imm32 is None or not self.hwnd:
            return
        try:
            prev = imm32.ImmAssociateContext(self.hwnd, None)
            self._ime_ctx = prev
        except Exception:
            self._ime_ctx = None

    def enable_ime(self):
        if imm32 is None or not self.hwnd:
            return
        if self._ime_ctx is None:
            return
        try:
            imm32.ImmAssociateContext(self.hwnd, self._ime_ctx)
        except Exception:
            pass
        self._ime_ctx = None

    def ime_open_for_window(self):
        """WPS 焦点窗口的输入法是否处于“打开”状态（中文模式）。

        手动按键模式用它判定：输入法开着 → 按键整体放行（用户可随时用
        中文输入法手动打字/修改）；输入法关闭（英文态）→ 普通按键被吞掉
        用于驱动摸鱼打字。无 IME 上下文（纯英文键盘布局）视为关闭。
        """
        if imm32 is None:
            return False
        try:
            if not self._ensure_hwnd():
                return False
            fh = self.get_focus_hwnd()
            if not fh:
                return False
            himc = imm32.ImmGetContext(fh)
            if not himc:
                return False
            try:
                return bool(imm32.ImmGetOpenStatus(himc))
            finally:
                imm32.ImmReleaseContext(fh, himc)
        except Exception:
            return False

    # ---------- 段落导航（公文模板逐段输入用） ----------
    def send_combo(self, mod_vk, vk):
        """发送一个组合键（如 Ctrl+Home）。"""
        ev = [
            (mod_vk, 0, 0),
            (vk, 0, 0),
            (vk, 0, KEYEVENTF_KEYUP),
            (mod_vk, 0, KEYEVENTF_KEYUP),
        ]
        return self._attach_and_send(ev) == 4

    def goto_doc_start(self):
        """Ctrl+Home：把光标移到文档最前（公文模式重定位段落前调用）。"""
        return self.send_combo(VK_CONTROL, VK_HOME)

    def goto_next_paragraph(self):
        """跳到下一个段落并回到段首（公文模式：一段打完后移到下一段空样式段落）。"""
        ok1 = self.send_key(VK_DOWN)
        ok2 = self.send_key(VK_HOME)
        return ok1 and ok2

    # ---------- 输入 ----------
    def send_unicode_char(self, ch):
        """发送一个 BMP 字符（down+up）。"""
        code = ord(ch)
        ev = [
            (0, code, KEYEVENTF_UNICODE),
            (0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
        ]
        return self._attach_and_send(ev) == 2

    def send_key(self, vk):
        """发送一个虚拟键（如回车 / Tab）。"""
        ev = [
            (vk, 0, 0),
            (vk, 0, KEYEVENTF_KEYUP),
        ]
        return self._attach_and_send(ev) == 2

    def _attach_and_send(self, events):
        """SendInput 注入到 WPS 线程上下文，规避后台进程的“前台锁”拦截。

        直接 SendInput 时，若当前进程不是前台进程，键盘事件常被 Windows 静默丢弃
        （与 SetForegroundWindow 同源限制）。把本线程临时挂到 WPS 窗口所属线程后，
        事件即被当作前台线程输入送达 WPS。失败时回退到普通 SendInput。
        """
        if not events:
            return 0
        our = kernel32.GetCurrentThreadId()
        target_tid = 0
        try:
            if self.hwnd and getattr(user32, "IsWindow", None) and user32.IsWindow(self.hwnd):
                target_tid = _window_tid(self.hwnd)
        except Exception:
            target_tid = 0
        attached = False
        if target_tid and target_tid != our and getattr(user32, "AttachThreadInput", None):
            try:
                user32.AttachThreadInput(our, target_tid, True)
                attached = True
            except Exception:
                attached = False
        try:
            return _send_input_list(events)
        finally:
            if attached:
                try:
                    user32.AttachThreadInput(our, target_tid, False)
                except Exception:
                    pass

    # ---------- 剪贴板兜底 ----------
    def _get_clipboard_text(self):
        """读取当前剪贴板文本（UTF-16）；失败返回空串。"""
        if not user32.OpenClipboard(0):
            return ""
        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return ""
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            p = kernel32.GlobalLock(h)
            if not p:
                return ""
            try:
                size = kernel32.GlobalSize(h)
                buf = ctypes.create_unicode_buffer(max(1, size // 2))
                ctypes.memmove(buf, p, min(size, ctypes.sizeof(buf)))
                return buf.value
            finally:
                kernel32.GlobalUnlock(h)
        finally:
            user32.CloseClipboard()

    def _set_clipboard_text(self, text):
        """把文本写入剪贴板（UTF-16）；返回是否成功。"""
        if not user32.OpenClipboard(0):
            return False
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h:
                return False
            p = kernel32.GlobalLock(h)
            ctypes.memmove(p, data, len(data))
            kernel32.GlobalUnlock(h)
            user32.SetClipboardData(CF_UNICODETEXT, h)
            return True
        finally:
            user32.CloseClipboard()

    def send_ctrl_v(self, text):
        """通过 Ctrl+V 粘贴 text（兜底路径，一次粘贴整段）。返回是否成功。"""
        old = self._get_clipboard_text()
        if not self._set_clipboard_text(text):
            return False
        ev = [
            (VK_CONTROL, 0, 0),
            (VK_V, 0, 0),
            (VK_V, 0, KEYEVENTF_KEYUP),
            (VK_CONTROL, 0, KEYEVENTF_KEYUP),
        ]
        ok = _send_input_list(ev) == 4
        # 还原剪贴板原内容，避免污染用户剪贴板
        try:
            self._set_clipboard_text(old)
        except Exception:
            pass
        return ok

    def type_char(self, ch):
        """把一个字符送进 WPS 文档。

        首选 WM_CHAR 直投焦点画布：中文输入法开启时，SendInput 的
        KEYEVENTF_UNICODE 注入会被 IME 组合窗口整个吞掉（EA 语系 IME 通病，
        实测 WPS 下 Ctrl 组合键可达而字符全丢，文档空白），而 WM_CHAR
        不经过键盘与 IME 链路，中英文均可直达文档。失败时依次回退
        SendInput Unicode 注入、剪贴板粘贴。
        """
        if ch == "\r":
            return True
        if ch == "\n":
            # 回车/制表是控制键，IME 不会吞，走 SendInput 最可靠；
            # 实测 WPS 画布对 WM_CHAR 0x0D 不生成段落标记，故不作首选。
            if self.send_key(VK_RETURN):
                return True
            return self._post_wm_code(0x0D)
        if ch == "\t":
            if self.send_key(VK_TAB):
                return True
            return self._post_wm_code(0x09)
        units = self._utf16_units(ch)
        if all(self._post_wm_code(ord(u)) for u in units):
            return True
        # WM_CHAR 失败（窗口失效等）→ SendInput Unicode 兜底 → 剪贴板兜底
        ok = self.send_unicode_char(ch)
        if not ok:
            try:
                return self.send_ctrl_v(ch)
            except Exception:
                return False
        return ok

    # ---------- WM_CHAR 直投（IME 免疫） ----------
    @staticmethod
    def _utf16_units(ch):
        """把字符拆成 UTF-16 码元（BMP 一段，增补字符为代理对两段）。"""
        cp = ord(ch)
        if cp < 0x10000:
            return [ch]
        cp -= 0x10000
        return [chr(0xD800 + (cp >> 10)), chr(0xDC00 + (cp & 0x3FF))]

    def get_focus_hwnd(self, refresh=False):
        """返回 WPS 内当前持有键盘焦点的子窗口（文档画布，类名 _WwG）。

        优先用 GetGUIThreadInfo 查 WPS 输入线程的真实焦点窗口；焦点若停在
        顶层框架窗口上（框架不接字符），则退而找 _WwG 画布子窗口。句柄缓存
        每 200 字刷新一次，防止 WPS 重建画布后句柄失效。
        """
        if (self._type_hwnd and not refresh and self._type_count < 200
                and user32.IsWindow(self._type_hwnd)):
            return self._type_hwnd
        if not self._ensure_hwnd():
            return None
        fh = None
        gti = _GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(_GUITHREADINFO)
        tid = _window_tid(self.hwnd)
        if tid and user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
            fh = gti.hwndFocus or None
        if fh == self.hwnd:  # 焦点在顶层框架上 → 视为无有效焦点
            fh = None
        if not fh:
            fh = self._find_wwg_child() or self.hwnd
        self._type_hwnd = fh
        self._type_count = 0
        return fh

    def _find_wwg_child(self):
        """在 WPS 主窗口下找类名为 _WwG 的文档画布子窗口（找不到返回 None）。"""
        hits = []

        def cb(h, lp):
            b = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, b, 64)
            if b.value == "_WwG":
                hits.append(h)
                return 0
            return 1

        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        try:
            user32.EnumChildWindows(self.hwnd, CB(cb), 0)
        except Exception:
            pass
        return hits[0] if hits else None

    def _post_wm_code(self, code):
        """向焦点画布直投一个 WM_CHAR 码元；失败时刷新目标句柄重试一次。"""
        target = self.get_focus_hwnd()
        if not target:
            return False
        if user32.PostMessageW(target, WM_CHAR, code & 0xFFFF, 0):
            self._type_count += 1
            return True
        target = self.get_focus_hwnd(refresh=True)
        if target and user32.PostMessageW(target, WM_CHAR, code & 0xFFFF, 0):
            self._type_count += 1
            return True
        return False

    # ---------- 关闭 ----------
    def close(self):
        self.enable_ime()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

# -*- coding: utf-8 -*-
"""全局低级键盘钩子（WH_KEYBOARD_LL）。

用途：在“摸鱼模式”下拦截用户按下的任意普通按键，把它吞掉（不让原键进入 WPS），
改由控制器把预载文档的下一个字经 WPS 驱动器打入真实 WPS 窗口。

设计要点：
  - 仅拦截普通按键（WM_KEYDOWN 且非修饰键、非 Ctrl/Alt/Win 组合），其余一律放行，
    保证 Alt+Tab、Ctrl+S、Win 等系统快捷键仍可正常使用，且用户在控制面板里打字不受影响。
  - 钩子回调只做“判定 + 入队”，真正的 SendInput 放在 Qt 定时器里执行，
    避免在低级输入回调中调用 SendInput 引发死锁/卡顿。
  - 回调对象必须长期持有引用，否则被 GC 后钩子失效。
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100

# KBDLLHOOKSTRUCT.flags 标志位
# 注意：LLKHF_INJECTED = 0x10（由 SendInput 等注入的事件），
# 而 0x01 是 LLKHF_EXTENDED（扩展键），两者极易混淆。务必用 0x10 判定“自己注入的事件”。
LLKHF_INJECTED = 0x10
LLKHF_ALTDOWN = 0x20

# 修饰键 / 系统键（一律放行，不拦截）
_MODIFIER_VKS = {
    0x10,  # VK_SHIFT
    0x11,  # VK_CONTROL
    0x12,  # VK_MENU (Alt)
    0x5B,  # VK_LWIN
    0x5C,  # VK_RWIN
    0x14,  # VK_CAPITAL (CapsLock)
    0x90,  # VK_NUMLOCK
    0x91,  # VK_SCROLL
}

LLKHF_ALTDOWN = 0x20


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class KeyboardInterceptor:
    """低级键盘拦截器。"""

    def __init__(self):
        self._handler = None   # callable(vk, flags) -> bool（True=吞掉）
        self._hook = None
        self._proc = None

    def is_active(self):
        return self._hook is not None

    def start(self, handler):
        """安装钩子。handler(vk, flags) 返回 True 表示吞掉该按键。"""
        if self._hook:
            return
        self._handler = handler
        self._proc = self._LOWLEVELKBPROC(self._callback)
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, None, 0
        )

    def stop(self):
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._proc = None
        self._handler = None

    def _callback(self, nCode, wParam, lParam):
        if nCode == 0 and wParam == WM_KEYDOWN:
            ks = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            vk = ks.vkCode
            flags = ks.flags
            if self._handler and self._handler(vk, flags):
                # 吞掉：返回非 0，且不要调用 CallNextHookEx
                return 1
        # 放行
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    @staticmethod
    def _LOWLEVELKBPROC(fn):
        return ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)(fn)


def modifier_held():
    """是否有 Ctrl / Alt / Win 处于按下状态（用于放行组合键）。"""
    if user32.GetAsyncKeyState(0x11) & 0x8000:
        return True
    if user32.GetAsyncKeyState(0x12) & 0x8000:
        return True
    if user32.GetAsyncKeyState(0x5B) & 0x8000 or user32.GetAsyncKeyState(0x5C) & 0x8000:
        return True
    return False

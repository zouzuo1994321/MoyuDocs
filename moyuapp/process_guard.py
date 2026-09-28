# -*- coding: utf-8 -*-
"""进程守护：启动时清理残留实例，退出时确保自身进程完全关闭。"""

import os
import sys
import ctypes
from ctypes import wintypes


def _exe_stem() -> str:
    if getattr(sys, "frozen", False):
        return os.path.splitext(os.path.basename(sys.executable))[0]
    return ""  # 开发模式不按名字清理，避免误杀其它 python 进程


def _snapshot_pids_by_name(name_lower: str):
    """用 Win32 工具快照枚举同名进程 PID。"""
    TH32CS_SNAPPROCESS = 0x2

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pids = []
    if snap == -1:
        return pids
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        if entry.szExeFile.lower() == name_lower:
            pids.append(entry.th32ProcessID)
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return pids


def cleanup_stale_processes():
    """启动时清理之前未关闭的残留自身进程（排除当前 PID）。"""
    stem = _exe_stem()
    if not stem:
        return 0
    me = os.getpid()
    killed = 0
    PROCESS_TERMINATE = 0x1
    k32 = ctypes.windll.kernel32
    for pid in _snapshot_pids_by_name(stem.lower() + ".exe"):
        if pid == me:
            continue
        h = k32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            k32.TerminateProcess(h, 0)
            k32.CloseHandle(h)
            killed += 1
    return killed


def ensure_exit(exit_code: int = 0):
    """强制结束自身进程，保证关闭后不残留。"""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    ctypes.windll.kernel32.ExitProcess(exit_code)

# -*- coding: utf-8 -*-
"""摸鱼文书 v2 离屏冒烟测试（真 WPS 驱动模式，不实际拉起 WPS）。

用法（managed python，QT_QPA_PLATFORM=offscreen）：
    python tests/smoke.py
"""

import os
import sys
import json
import struct
import ctypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("✅ " if cond else "❌ ") + name + ("" if cond else f"  {extra}"))


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    samples = os.path.join(base, "samples")

    from moyuapp import docimport, wps_driver, keyboard_hook
    from moyuapp.controller import ControllerWindow

    # 1) 文档导入
    txt = os.path.join(samples, "摸鱼文化建设试点通知.txt")
    if os.path.exists(txt):
        blocks = docimport.import_file(txt)
        check("导入 TXT 非空", len(blocks) > 5, str(len(blocks)))
        check("TXT 首段识别为公文大标题", blocks[0]["level"] == -1, str(blocks[0]))
        lv = {b["level"] for b in blocks if b["level"] > 0}
        check("TXT 识别多级标题 1/2/3", {1, 2, 3} <= lv, str(sorted(lv)))
    else:
        check("示例 TXT 存在", False, txt)

    # 2) WPS 路径探测（本机应装了 WPS 个人版）
    wp = wps_driver.find_wps_path()
    check("探测到 wps.exe", bool(wp), str(wp))

    # 3) SendInput 字节缓冲打包正确（unicode 事件）
    buf = wps_driver._pack_input(0, ord("中"), wps_driver.KEYEVENTF_UNICODE)
    vk, scan, flags = struct.unpack_from("<HHI", buf, 0)
    check("打包长度 28 字节", len(buf) == 28)
    check("unicode 事件 wVk=0", vk == 0)
    check("unicode 事件 wScan=中", scan == ord("中"))
    check("unicode 事件 flags=UNICODE", flags == wps_driver.KEYEVENTF_UNICODE)

    # 3b) INPUT 结构体大小必须为 40（64 位 Windows），否则 SendInput 静默失败
    check("INPUT 结构体大小=40", ctypes.sizeof(wps_driver.INPUT) == 40, str(ctypes.sizeof(wps_driver.INPUT)))

    # 3c) 用 mock 校验 SendInput 组装的字段正确（不真正发键，避免误伤系统）
    captured = {}
    class _FakeUser32:
        pass
    fake = _FakeUser32()
    def _fake_send(n, p, cb):
        arr = ctypes.cast(p, ctypes.POINTER(wps_driver.INPUT * n)).contents
        captured["n"] = n
        captured["arr"] = [(a.type, a.u.ki.wVk, a.u.ki.wScan, a.u.ki.dwFlags) for a in arr]
        return n
    fake.SendInput = _fake_send
    _orig = wps_driver.user32
    wps_driver.user32 = fake
    try:
        res = wps_driver._send_input_list([
            (0, ord("中"), wps_driver.KEYEVENTF_UNICODE),
            (0, ord("中"), wps_driver.KEYEVENTF_UNICODE | wps_driver.KEYEVENTF_KEYUP),
        ])
    finally:
        wps_driver.user32 = _orig
    check("SendInput 发出 2 个事件", res == 2 and captured.get("n") == 2, str(captured.get("n")))
    evs = captured.get("arr", [])
    check("unicode 按下事件字段正确", evs and evs[0] == (1, 0, ord("中"), wps_driver.KEYEVENTF_UNICODE), str(evs))
    check("unicode 抬起事件字段正确",
          len(evs) > 1 and evs[1] == (1, 0, ord("中"), wps_driver.KEYEVENTF_UNICODE | wps_driver.KEYEVENTF_KEYUP),
          str(evs))

    # 3d) current_foreground_image 诊断函数可调用
    check("current_foreground_image 可调用返回 str", isinstance(wps_driver.current_foreground_image(), str))

    # 4) 键盘钩子构造 + 启停无异常
    inter = keyboard_hook.KeyboardInterceptor()
    try:
        inter.start(lambda vk, flags: False)
        ok_start = inter.is_active()
        inter.stop()
        ok_stop = not inter.is_active()
    except Exception as e:
        ok_start = ok_stop = False
        print("   hook error:", e)
    check("键盘钩子可启停", ok_start and ok_stop)

    # 5) 控制面板构建 + 导入 + 目录
    win = ControllerWindow()
    win.show()
    app.processEvents()
    check("控制面板构建成功", win is not None)

    if os.path.exists(txt):
        # 清空上次运行遗留的进度文件，保证从 0 开始、测试可重复
        _prog = os.path.join(os.path.expandvars("%APPDATA%"), "摸鱼文书", "progress.json")
        if os.path.exists(_prog):
            try:
                os.remove(_prog)
            except Exception:
                pass
        win._load_file(txt)
        check("导入后总字数>0", win._total > 0, str(win._total))
        check("目录列表已填充", win.lst_outline.count() > 3, str(win.lst_outline.count()))
        check("进度初始 0", win._index == 0)

    # 6) 用桩驱动模拟逐字打入（不拉起真 WPS）
    class StubDriver:
        pid = 999
        def __init__(self):
            self.sent = []
            self.ime_open = False
        def is_alive(self):
            return True
        def is_foreground(self):
            return True
        def focus(self):
            return True
        def type_char(self, ch):
            self.sent.append(ch)
            return True
        def ime_open_for_window(self):
            return self.ime_open

    stub = StubDriver()
    win._driver = stub
    win._active = True
    win._index = 0
    stub.sent.clear()
    # 模拟“按任意键”→ 钩子入队 → 定时器抽干 → 逐字打入
    for _ in range(15):
        assert win._on_key(0x41, 0) is True  # 吞掉普通键并入队
    for _ in range(15):
        win._drain()
    check("手动模式 15 次按键 -> 打出 15 字", stub.sent and len(stub.sent) == 15, str(len(stub.sent)))
    check("进度推进到 15", win._index == 15, str(win._index))
    check("进度百分比=100*15/total",
          win.bar.value() == (1500 // win._total if win._total else 0))

    # 6c) send_ctrl_v 打包校验（mock 全部 Win32 调用，避免误触系统剪贴板）
    class _ClipFaker:
        def __init__(self):
            self.send_n = 0
        def OpenClipboard(self, *a): return True
        def CloseClipboard(self, *a): return True
        def EmptyClipboard(self, *a): return True
        def IsClipboardFormatAvailable(self, f): return True
        def GetClipboardData(self, f): return 1
        def SetClipboardData(self, f, h): return h
        def GetForegroundWindow(self): return 1
        def GetWindowThreadProcessId(self, h, p): return 1
        def GetCurrentThreadId(self): return 1
        def SetForegroundWindow(self, h): return True
        def ShowWindow(self, h, n): return True
        def GetWindowRect(self, h, r): return True
        def SetCursorPos(self, x, y): return True
        def mouse_event(self, *a): return True
        def AllowSetForegroundWindow(self, x): return True
        def AttachThreadInput(self, a, b, c): return True
    fuser = _ClipFaker()
    fkern = _ClipFaker()
    fkern.GlobalAlloc = lambda fl, sz: 1
    fkern.GlobalLock = lambda h: ctypes.create_string_buffer(1024)
    fkern.GlobalUnlock = lambda h: True
    fkern.GlobalSize = lambda h: 1024

    # SendInput 必须是可设 .argtypes 的普通函数（不能是实例方法）
    def _fake_sendinput(n, p, cb):
        fuser.send_n = n
        return n
    fuser.SendInput = _fake_sendinput

    _ou, _ok = wps_driver.user32, wps_driver.kernel32
    wps_driver.user32 = fuser
    wps_driver.kernel32 = fkern
    try:
        d = wps_driver.WpsDriver()
        d.hwnd = 1
        res = d.send_ctrl_v("测试")
    finally:
        wps_driver.user32 = _ou
        wps_driver.kernel32 = _ok
    check("send_ctrl_v 走 Ctrl+V 路径(4 事件)", fuser.send_n == 4, str(fuser.send_n))
    check("send_ctrl_v 返回成功", res is True, str(res))

    # 6d) WM_CHAR 直投路径（IME 免疫）：type_char 应走 PostMessageW(WM_CHAR)
    class _CharFaker:
        def __init__(self):
            self.posts = []
            self.send_n = 0
        def IsWindow(self, h): return True
        def IsWindowVisible(self, h): return True
        def GetGUIThreadInfo(self, tid, p): return True
        def GetWindowThreadProcessId(self, h, p): return 1
        def PostMessageW(self, h, msg, wp, lp):
            self.posts.append((h, msg, wp)); return True
        def SendInput(self, n, p, cb):
            self.send_n = n; return n

    fch = _CharFaker()

    def _fch_send(n, p, cb):
        fch.send_n = n
        return n
    fch.SendInput = _fch_send  # 普通函数（_send_input_list 会设 argtypes）
    _ou2 = wps_driver.user32
    wps_driver.user32 = fch
    try:
        d2 = wps_driver.WpsDriver()
        d2.hwnd = 42
        d2._type_hwnd = 42  # 直接命中缓存，不触发窗口枚举
        r1 = d2.type_char("A")
        r2 = d2.type_char("\n")
        r3 = d2.type_char("𠀀")  # 增补字符 → 代理对两段
    finally:
        wps_driver.user32 = _ou2
    check("type_char('A') 走 WM_CHAR", r1 and fch.posts[:1] == [(42, 0x0102, 65)], str(fch.posts))
    check("type_char('\\n') 走 SendInput 回车(2 事件)",
          r2 and fch.send_n == 2 and (42, 0x0102, 0x0D) not in fch.posts,
          "send_n=%s posts=%s" % (fch.send_n, fch.posts))
    check("增补字符拆为代理对两段", r3 and [p[2] for p in fch.posts[-2:]] == [0xD840, 0xDC00],
          str(fch.posts[-2:]))

    # 6e) WM_CHAR 失败时回退 SendInput
    class _CharFail(_CharFaker):
        def PostMessageW(self, *a): return False
    fcf = _CharFail()

    def _plain_send(n, p, cb):
        fcf.send_n = n
        return n
    fcf.SendInput = _plain_send  # 必须是普通函数（_send_input_list 会设 argtypes）
    wps_driver.user32 = fcf
    try:
        d3 = wps_driver.WpsDriver()
        d3.hwnd = 42
        d3._type_hwnd = 42
        rf = d3.type_char("B")
    finally:
        wps_driver.user32 = _ou2
    check("WM_CHAR 失败回退 SendInput(2 事件)", rf and fcf.send_n == 2, str(fcf.send_n))

    # 7) 钩子对“自己注入的事件”(LLKHF_INJECTED=0x10) 放行（避免递归吞掉自己的字）
    check("自身注入事件被放行(0x10)", win._on_key(0x41, 0x10) is False)
    # 激活态下，即便 WPS 前台，注入事件仍应放行
    win._driver = stub  # stub.is_foreground() == True
    win._active = True
    check("激活态下自身注入事件仍放行", win._on_key(0x41, 0x10) is False)
    # 8) 修饰键放行
    check("修饰键放行", win._on_key(0x11, 0) is False)
    # 9) F9 切换（返回 True 表示已消费）
    win._active = False
    check("F9 触发切换", win._on_key(0x78, 0) is True)

    # 9a) 失焦锁定 / 自动打字功能已移除
    check("失焦锁定已移除", not hasattr(win, "chk_autofocus") and not hasattr(win, "_auto_focus"))
    check("自动打字已移除", not hasattr(win, "chk_autotype") and not hasattr(win, "_auto_type"))

    # 9b) 手动模式：退格/删除/方向等编辑键放行（真实删字、移动光标）
    win._driver = stub
    win._active = True
    stub.ime_open = False
    win._queue.clear()
    for vk, name in [(0x08, "Backspace"), (0x2E, "Delete"), (0x25, "←"),
                     (0x26, "↑"), (0x27, "→"), (0x28, "↓"),
                     (0x21, "PgUp"), (0x22, "PgDn"), (0x23, "End"), (0x24, "Home")]:
        ok = win._on_key(vk, 0) is False and not win._queue
        check(f"手动模式 {name} 放行", ok)
    # 9c) 手动模式：输入法打开 → 普通键放行（可手动打字）；关闭 → 吞键驱动
    stub.ime_open = True
    check("输入法打开时普通键放行", win._on_key(0x41, 0) is False and not win._queue)
    stub.ime_open = False
    check("输入法关闭时普通键吞掉驱动", win._on_key(0x41, 0) is True and len(win._queue) == 1)
    win._queue.clear()
    win._active = False

    # 9d) 顶部 logo 已移除 + 底部提示已精简（防截断）
    check("顶部 logo 已移除", not hasattr(win, "lbl_logo"))
    check("底部提示已精简", hasattr(win, "lbl_tip") and len(win.lbl_tip.text()) <= 120,
          str(len(win.lbl_tip.text()) if hasattr(win, "lbl_tip") else -1))

    # 10) 进度保存 / 恢复
    win._file_path = txt
    prog = os.path.join(os.path.expandvars("%APPDATA%"), "摸鱼文书", "progress.json")
    win._save_progress()
    if os.path.exists(prog):
        d = json.load(open(prog, encoding="utf-8"))
        check("进度文件含 index", d.get("index") == win._index, str(d))
    else:
        check("进度文件写入", False, prog)

    # 11) 皮肤切换
    win._dark = True
    win._on_skin()
    check("皮肤可切换为亮", win._dark is False)
    win._on_skin()
    check("皮肤可切换回暗", win._dark is True)

    # 12) 公文排版（GB/T 9704-2012）模板生成
    from moyuapp import gongwen as gmod
    sample_blocks = [
        {"text": "关于开展摸鱼文化建设试点的通知", "level": -1},
        {"text": "各有关单位：", "level": 0},
        {"text": "一、总体要求", "level": 1},
        {"text": "坚持以人民为中心的发展思想。", "level": 0},
        {"text": "（一）基本原则", "level": 2},
        {"text": "1. 稳妥推进。", "level": 3},
    ]
    gpath = os.path.join(base, "samples", "_gongwen_test.docx")
    try:
        if os.path.exists(gpath):
            os.remove(gpath)
    except Exception:
        pass
    fonts = gmod.build_docx(gpath, sample_blocks, families=["宋体", "黑体", "楷体_GB2312", "仿宋_GB2312"])
    check("公文模板生成成功", os.path.exists(gpath) and os.path.getsize(gpath) > 0)
    if os.path.exists(gpath):
        import zipfile as _zf
        with _zf.ZipFile(gpath) as z:
            names = set(z.namelist())
            doc_xml = z.read("word/document.xml").decode("utf-8", "replace")
            settings_xml = z.read("word/settings.xml").decode("utf-8", "replace")
            footer_xml = z.read("word/footer1.xml").decode("utf-8", "replace")
        check("公文模板含 document.xml", "word/document.xml" in names)
        check("公文模板含页脚/设置",
              {"word/footer1.xml", "word/footer2.xml", "word/settings.xml"} <= names)
        # 每个块对应一个独立空样式段落（<w:p><w:pPr>）
        para_count = doc_xml.count("<w:p><w:pPr>")
        check("公文模板段落数=块数", para_count == len(sample_blocks),
              f"{para_count} vs {len(sample_blocks)}")
        check("公文模板含国标页边距(上37mm)", "w:top=\"%s\"" % gmod.MARGIN_TOP in doc_xml)
        check("公文模板含奇偶页页脚设置", "evenAndOddHeaders" in settings_xml)
        check("公文模板标题用宋体(无小标宋回退)", "方正小标宋" not in doc_xml and "宋体" in doc_xml)
        check("公文模板正文用仿宋", "仿宋" in doc_xml)
        check("公文模板页码一字线包裹", "— " in footer_xml)
    try:
        if os.path.exists(gpath):
            os.remove(gpath)
    except Exception:
        pass

    # 13) 控制器：公文模式段落定位（桩驱动，不拉起 WPS，无模态对话框）
    class NavStub:
        pid = 123
        def __init__(self):
            self.calls = []
        def is_alive(self): return True
        def is_foreground(self): return True
        def focus(self): return True
        def goto_doc_start(self):
            self.calls.append("start")
        def goto_next_paragraph(self):
            self.calls.append("next")
        def type_char(self, ch):
            return True
    nav = NavStub()
    win._driver = nav
    win._active = True
    win._gongwen = True
    # 构造 4 个块（3 个换行）的文本，定位到第 3 段（_index 在第三个块中）
    win._blocks = [
        {"text": "标题一", "level": -1},
        {"text": "第一段", "level": 0},
        {"text": "第二段", "level": 1},
        {"text": "第三段", "level": 0},
    ]
    win._doc_text = "\n".join(b["text"] for b in win._blocks)
    # 第三段开头：前面有 2 个换行 → 段落偏移 = 2
    win._index = len("标题一\n第一段\n第二段") + 1  # 落在“第三段”首字（第 4 块，段落偏移 3）
    nav.calls.clear()
    exp_next = win._doc_text.count("\n", 0, win._index)  # _index 之前的换行数 = 目标段落偏移
    win._position_cursor_to_index()
    check("公文定位先回到文档最前", nav.calls and nav.calls[0] == "start", str(nav.calls))
    check("公文定位下移段数=目标段落偏移", nav.calls.count("next") == exp_next, str(nav.calls))
    win._gongwen = False

    # 14) 控制器：公文模式逐字输入会“跳段”（验证 _reveal_one 换行处理，无需 WPS）
    class GongwenTypingStub:
        pid = 7
        def __init__(self):
            self.typed = []
            self.paras = 0
            self.alive = True
        def is_alive(self): return self.alive
        def is_foreground(self): return True
        def focus(self): return True
        def type_char(self, ch):
            self.typed.append(ch); return True
        def goto_next_paragraph(self):
            self.paras += 1
    gstub = GongwenTypingStub()
    win._driver = gstub
    win._active = True
    win._gongwen = True
    win._blocks = [{"text": "标题"}, {"text": "甲"}, {"text": "乙"}, {"text": "丙"}]
    win._doc_text = "\n".join(b["text"] for b in win._blocks)  # 标题\n甲\n乙\n丙
    win._total = len(win._doc_text)
    win._index = 0
    for _ in range(win._total):
        win._reveal_one()
    check("公文模式逐字输入覆盖全部字符", "".join(gstub.typed) == "标题甲乙丙", "".join(gstub.typed))
    check("公文模式换行触发跳段次数=块数-1", gstub.paras == len(win._blocks) - 1, str(gstub.paras))
    check("公文模式打完进度到达末尾", win._index == win._total, str(win._index))
    win._gongwen = False

    # 15) 假弹窗广告（右下角）
    from moyuapp import ad_popup
    p = ad_popup.AdPopup("image", "", "")
    check("广告弹窗可创建", p is not None)
    check("广告弹窗尺寸固定", p.width() == ad_popup.AD_W and p.height() == ad_popup.AD_H,
          f"{p.width()}x{p.height()}")
    fl = p.windowFlags()
    check("广告弹窗无边框+置顶+工具窗",
          bool(fl & Qt.FramelessWindowHint) and bool(fl & Qt.WindowStaysOnTopHint)
          and bool(fl & Qt.Tool), hex(int(fl)))
    p.reveal()
    app.processEvents()
    check("广告弹窗可显示", p.isVisible())
    p.shutdown()
    check("广告弹窗可关闭", not p.isVisible())

    # 15b) 网页/视频模式：大窗口可拉伸（不实际加载内容，离屏环境不建 WebEngine）
    purl = ad_popup.AdPopup("url", "https://example.com", "")
    check("网页模式大窗口", purl.width() == ad_popup.AD_BIG_W and purl.height() == ad_popup.AD_BIG_H,
          f"{purl.width()}x{purl.height()}")
    check("网页模式可拉伸(非固定尺寸)",
          purl.maximumSize().width() > purl.width(),
          f"max={purl.maximumSize().width()} w={purl.width()}")
    purl.shutdown()
    pvid = ad_popup.AdPopup("video", "", "不存在.mp4")
    check("视频模式大窗口", pvid.width() == ad_popup.AD_BIG_W and pvid.height() == ad_popup.AD_BIG_H)
    pvid.shutdown()

    # 15f) v2.0.9：网页模式“系统浏览器打开”按钮 + 直链视频扩展名表
    check("网页模式带系统浏览器按钮", hasattr(purl, "_btn_browser"))
    check("视频模式无浏览器按钮", not hasattr(pvid, "_btn_browser"))
    check("直链视频扩展名表", ".mp4" in ad_popup._MEDIA_EXTS and ".webm" in ad_popup._MEDIA_EXTS)

    # 15c) 控制器弹出 / 关闭广告
    win._ad_enabled = True
    win._ad_delay_sec = 10
    win._ad_mode = "image"
    win._ad_url = ""
    win._show_ad()
    check("控制器弹出广告", win._ad_popup is not None and win._ad_popup.isVisible())
    win._close_ad()
    check("控制器关闭广告", win._ad_popup is None)

    # 15d) 广告延迟最低 10 秒（定时器间隔=秒*1000）
    win._ad_enabled = True
    win._ad_delay_sec = 10
    win._arm_ad_timer()
    check("10 秒定时器已启动",
          win._ad_timer is not None and win._ad_timer.interval() == 10000
          and win._ad_timer.isActive(), str(win._ad_timer.interval() if win._ad_timer else None))
    win._ad_enabled = False
    win._disarm_ad_timer()
    win._ad_enabled = True
    win._ad_delay_sec = 5  # 低于 10 秒不应启动
    win._arm_ad_timer()
    check("低于 10 秒不启动", win._ad_timer is None)
    win._ad_delay_sec = 300

    # 15e) 广告配置持久化（按秒）
    win._ad_enabled = True
    win._ad_delay_sec = 45
    win._ad_mode = "url"
    win._ad_url = "https://example.com/ad"
    win._save_config()
    win2 = ControllerWindow()
    check("广告配置可持久化",
          win2._ad_enabled and win2._ad_delay_sec == 45
          and win2._ad_mode == "url" and win2._ad_url == "https://example.com/ad",
          f"{win2._ad_enabled},{win2._ad_delay_sec},{win2._ad_mode},{win2._ad_url}")
    # UI 回填：45 秒非整分钟 → 应显示“45 秒”
    check("延迟 UI 回填为秒", win2.spin_ad_delay.value() == 45
          and win2.cmb_ad_unit.currentIndex() == 1,
          f"{win2.spin_ad_delay.value()},{win2.cmb_ad_unit.currentIndex()}")
    # 恢复默认，避免污染后续真实运行的配置
    win2._ad_enabled = False
    win2._ad_delay_sec = 300
    win2._ad_mode = "image"
    win2._ad_url = ""
    win2._save_config()
    win2.close()

    # 16) v2.0.9：关于对话框联系方式 + 关闭即退出
    contacts = ControllerWindow._CONTACTS
    urls = " ".join(u for _, _, u in contacts)
    check("关于含 GitHub/B站/微博/邮箱", bool(contacts) and all(
        k in urls for k in ("github.com", "bilibili.com", "weibo.com", "mailto:")),
        urls)
    check("联系方式图标资源存在",
          all(os.path.exists(ad_popup._res_path("assets", n)) for n, _, _ in contacts))
    check("关闭即退出(强制杀死兜底)", hasattr(win, "_force_kill_later"))

    win.close()

    print(f"\n===== v2 冒烟结果：{len(PASS)} 通过 / {len(FAIL)} 失败 =====")
    if FAIL:
        print("失败项：", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()

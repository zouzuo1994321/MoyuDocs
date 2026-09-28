# -*- coding: utf-8 -*-
"""摸鱼文书 入口（v2：真 WPS 驱动模式）。

Copyright 2026 肆月Aperture
本软件为开源软件，没有授权禁止用于商业用途。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import traceback
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from moyuapp.process_guard import cleanup_stale_processes, ensure_exit
        from moyuapp.controller import ControllerWindow

        # 启动即清理之前未关闭的残留自身进程
        cleanup_stale_processes()

        # QtWebEngine（假弹窗广告加载网页用）要求在 QApplication 创建前共享 GL 上下文
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

        app = QApplication(sys.argv)
        app.setApplicationName("摸鱼文书")
        app.setOrganizationName("肆月Aperture")
        app.setStyle("Fusion")

        win = ControllerWindow()
        win.show()

        code = app.exec()
        # 关闭后确保自身进程完全退出
        ensure_exit(code)
    except Exception:
        # 把未捕获异常写入崩溃日志，便于排查（TEMP/moyu_crash.log）
        tb = traceback.format_exc()
        try:
            with open(os.path.join(os.environ.get("TEMP", "."), "moyu_crash.log"), "w", encoding="utf-8") as _f:
                _f.write(tb)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()

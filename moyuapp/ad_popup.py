# -*- coding: utf-8 -*-
"""假右下角弹窗广告（摸鱼气氛组）。

模拟真实网站的右下角小弹窗广告：
  - 默认广告图模式：380x250 无边框小窗，不出现在任务栏，弹出时不抢 WPS
    焦点（WS_EX_NOACTIVATE），摸鱼打字不中断；
  - 右上角“×”真关闭；
  - 中间区域可点击：按配置加载网页（内嵌 WebEngineView）或播放本地视频；
  - 网页/视频模式：窗口约为 400x260（大窗的 50%）且**可拉伸**，加载内容后
    移除 WS_EX_NOACTIVATE 并主动置前台——网页可正常点链接跳转/输入，
    视频带完整控制条（播放/暂停、进度拖动、音量）。
  - 网页/视频模式用普通顶层窗口（Qt.Window）而非 Qt.Tool，否则
    QWebEngineView 收不到鼠标/键盘输入、链接无法点击跳转。

仅做展示，不弹任何真实广告、不采集任何数据。
"""

import os
import sys
import ctypes

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QStackedWidget, QSlider,
    QHBoxLayout, QVBoxLayout, QSizePolicy, QSizeGrip,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

user32 = ctypes.windll.user32


class _AdWebPage(QWebEnginePage):
    """自定义网页：让 target="_blank" / window.open 在当前视图内打开，
    避免“点击链接没反应”（QWebEnginePage.createWindow 默认不处理新窗口）。"""

    def createWindow(self, type_):
        return self

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

AD_W, AD_H = 380, 250          # 广告图模式尺寸
AD_BIG_W, AD_BIG_H = 400, 260  # 网页/视频模式尺寸（约为大窗的 50%，可拉伸）

# 直链视频扩展名：PySide6 的 QtWebEngine 不含 H.264/AAC 专有编解码器，
# 网页里的 MP4 视频会报“不支持 HTML5 播放器”；直链视频改走 QMediaPlayer
# （Windows Media Foundation 后端，H.264 本地/远程均可播）。
_MEDIA_EXTS = (".mp4", ".m4v", ".webm", ".mov", ".mkv", ".ts")

# 无图 / 图缺失时的兜底样式（土味配色）
_FALLBACK_QSS = """
#AdRoot { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
             stop:0 #ff512f, stop:1 #dd2476);
           border:2px solid #ffd54f; border-radius:10px; }
#AdHeadline { color:#fff8e1; font-size:20px; font-weight:bold; background:transparent; }
#AdSub { color:#ffe082; font-size:12px; background:transparent; }
"""

_BAR_QSS = """
#adbar { background: rgba(0,0,0,160); }
#adbar QPushButton { background: rgba(255,255,255,30); color:#fff;
    border:none; border-radius:4px; padding:3px 10px; }
#adbar QPushButton:hover { background: rgba(255,255,255,60); }
#adbar QLabel { color:#fff; background:transparent; font-size:11px; }
#adbar QSlider::groove:horizontal { background: rgba(255,255,255,60); height:4px; border-radius:2px; }
#adbar QSlider::handle:horizontal { background:#ffd54f; width:10px; margin:-4px 0; border-radius:5px; }
"""


def _res_path(*parts):
    """打包后从 _MEIPASS 取资源，开发态从项目根取。"""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, *parts)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


def _default_ad_pixmap():
    p = _res_path("assets", "ad_default.png")
    if os.path.exists(p):
        pm = QPixmap(p)
        if not pm.isNull():
            return pm.scaled(AD_W, AD_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return None


def _fmt_ms(ms):
    if ms <= 0:
        return "00:00"
    s = int(ms // 1000)
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


class AdPopup(QWidget):
    """右下角假广告弹窗。mode: 'image' | 'url' | 'video'。"""

    def __init__(self, mode="image", url="", video_path="", parent=None):
        big = mode in ("url", "video")
        if big:
            # 交互型（网页/视频）：必须用普通顶层窗口 Qt.Window 而非 Qt.Tool，
            # 否则 QWebEngineView 收不到鼠标/键盘输入、链接无法点击跳转。
            flags = Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        else:
            flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self._mode = mode
        self._url = url
        self._video = video_path
        self._loaded = False
        self._player = None
        self._audio = None
        self._interactive = False
        self._big = big

        if big:
            self.resize(AD_BIG_W, AD_BIG_H)
            # 可缩到约 50%（400x260）之下的下限，保证“缩小到50%”真正生效
            self.setMinimumSize(280, 200)
        else:
            self.setFixedSize(AD_W, AD_H)
        self._build_ui(big)

    # ---------- UI ----------
    def _build_ui(self, big):
        self._stack = QStackedWidget(self)
        self._stack.setGeometry(0, 0, self.width(), self.height())

        base = QLabel()
        base.setObjectName("AdRoot")
        pm = _default_ad_pixmap()
        if pm is not None:
            base.setPixmap(pm)
            base.setScaledContents(True)
        else:
            base.setStyleSheet(_FALLBACK_QSS)
            bv = QVBoxLayout(base)
            bv.addStretch(1)
            head = QLabel("限时福利来袭！")
            head.setObjectName("AdHeadline")
            head.setAlignment(Qt.AlignCenter)
            sub = QLabel("恭喜获得会员体验资格 · 点击立即领取")
            sub.setObjectName("AdSub")
            sub.setAlignment(Qt.AlignCenter)
            bv.addWidget(head)
            bv.addWidget(sub)
            bv.addStretch(1)
        self._stack.addWidget(base)          # index 0：默认广告图
        self._stack.setCurrentIndex(0)

        # 浮层：左上“广告”角标 + 右上关闭
        self._lbl_tag = QLabel("广告", self)
        self._lbl_tag.setStyleSheet(
            "background:#000000; color:#ffd54f; font-size:11px;"
            "padding:1px 6px; border-radius:3px;"
        )
        self._lbl_tag.move(6, 6)
        self._lbl_tag.show()
        self._lbl_tag.raise_()

        self._btn_close = QPushButton("×", self)
        self._btn_close.setGeometry(self.width() - 28, 4, 24, 24)
        self._btn_close.setStyleSheet(
            "QPushButton { background:#7f0000; color:#fff; border:none;"
            " border-radius:12px; font-weight:bold; font-size:14px; }"
            "QPushButton:hover { background:#b71c1c; }"
        )
        self._btn_close.setToolTip("关闭广告")
        self._btn_close.clicked.connect(self.shutdown)
        self._btn_close.show()
        self._btn_close.raise_()

        # 可拉伸窗口：右下角 grip（网页/视频模式）
        if big:
            self._grip = QSizeGrip(self)
            self._grip.setFixedSize(16, 16)
            self._grip.show()
            self._grip.raise_()

        # 网页模式：左下角“系统浏览器打开”悬浮按钮。
        # 内嵌 WebEngine 不含 H.264/AAC 专有编解码器，B 站等视频站无法播放，
        # 提供一键跳转系统浏览器（真实 Chrome/Edge）观看。
        if big and self._mode == "url":
            self._btn_browser = QPushButton("🌐 系统浏览器打开", self)
            self._btn_browser.setToolTip(
                "内嵌浏览器不含 H.264 解码器，视频网站请用系统浏览器观看")
            self._btn_browser.setStyleSheet(
                "QPushButton { background:rgba(0,0,0,150); color:#fff;"
                " border:1px solid rgba(255,255,255,80); border-radius:10px;"
                " padding:3px 10px; font-size:11px; }"
                "QPushButton:hover { background:rgba(0,0,0,210); }")
            self._btn_browser.clicked.connect(self._open_in_browser)
            self._btn_browser.adjustSize()
            self._btn_browser.move(8, self.height() - self._btn_browser.height() - 8)
            self._btn_browser.show()
            self._btn_browser.raise_()

    def resizeEvent(self, ev):
        """窗口拉伸时同步堆叠容器/浮层按钮位置。"""
        try:
            self._stack.setGeometry(0, 0, self.width(), self.height())
            self._btn_close.move(self.width() - 28, 4)
            if getattr(self, "_grip", None) is not None:
                self._grip.move(self.width() - 16, self.height() - 16)
            if getattr(self, "_btn_browser", None) is not None:
                self._btn_browser.move(
                    8, self.height() - self._btn_browser.height() - 8)
        except Exception:
            pass
        super().resizeEvent(ev)

    def mousePressEvent(self, ev):
        """点击中间区域 → 加载配置的网页 / 视频（默认广告图模式无额外内容）。"""
        if ev.button() == Qt.LeftButton:
            self.open_content()
        super().mousePressEvent(ev)

    # ---------- 内容加载 ----------
    def open_content(self):
        if self._loaded:
            return
        try:
            if self._mode == "url" and self._url:
                self._open_url()
            elif self._mode == "video" and self._video and os.path.exists(self._video):
                self._open_video()
        except Exception:
            # 加载失败静默回退为默认广告图
            self._loaded = False
            self._stack.setCurrentIndex(0)
        if self._loaded:
            self._make_interactive()

    def _open_url(self):
        u = QUrl(self._url)
        # 直链视频（.mp4/.webm 等）：WebEngine 无 H.264 解码器 → 转 QMediaPlayer
        if u.path().lower().endswith(_MEDIA_EXTS):
            self._open_video(remote_url=self._url)
            return
        w = QWebEngineView()
        self._web = w
        # 用自定义页：target="_blank"/window.open 在当前视图内打开，
        # 点击链接即可跳转（默认 createWindow 不处理新窗口 → 点击无反应）。
        w.setPage(_AdWebPage(w))
        w.load(u)
        self._stack.addWidget(w)
        self._stack.setCurrentWidget(w)
        w.setFocus()
        self._loaded = True

    def _open_in_browser(self):
        """用系统默认浏览器打开当前网页（视频站等需要 H.264 的场景）。"""
        try:
            u = self._url
            web = getattr(self, "_web", None)
            if web is not None and not web.url().isEmpty():
                u = web.url().toString()
            QDesktopServices.openUrl(QUrl(u))
        except Exception:
            pass

    def _open_video(self, remote_url=None):
        """播放本地视频文件，或 remote_url 传入的直链视频（http(s)）。"""
        from PySide6.QtMultimedia import QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget

        # 视频页 = 视频画面 + 底部控制条（播放/暂停、进度、音量）
        page = QWidget()
        pv = QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        vw = QVideoWidget()
        vw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pv.addWidget(vw, 1)

        bar = QWidget()
        bar.setObjectName("adbar")
        bar.setStyleSheet(_BAR_QSS)
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(8, 4, 8, 4)
        bh.setSpacing(8)
        self._btn_play = QPushButton("⏸")
        self._btn_play.setFixedWidth(44)
        self._sld_pos = QSlider(Qt.Horizontal)
        self._sld_pos.setRange(0, 0)
        self._lbl_time = QLabel("00:00 / 00:00")
        self._lbl_time.setFixedWidth(110)
        self._lbl_time.setAlignment(Qt.AlignCenter)
        bh.addWidget(self._btn_play)
        bh.addWidget(self._sld_pos, 1)
        bh.addWidget(self._lbl_time)
        bh.addWidget(QLabel("🔊"))
        self._sld_vol = QSlider(Qt.Horizontal)
        self._sld_vol.setRange(0, 100)
        self._sld_vol.setValue(100)
        self._sld_vol.setFixedWidth(90)
        bh.addWidget(self._sld_vol)
        pv.addWidget(bar, 0)

        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        # 关键：QVideoWidget 不会自动连接播放器，必须显式 setVideoOutput，
        # 否则画面全黑（v2.0.6 黑屏根因）。
        self._player.setVideoOutput(vw)
        if remote_url:
            self._player.setSource(QUrl(remote_url))
        else:
            self._player.setSource(QUrl.fromLocalFile(self._video))
        self._audio.setVolume(1.0)

        self._btn_play.clicked.connect(self._toggle_play)
        self._player.playbackStateChanged.connect(self._on_play_state)
        self._player.positionChanged.connect(self._on_pos)
        self._player.durationChanged.connect(
            lambda d: (self._sld_pos.setRange(0, int(d)), self._upd_time(d, 0)))
        self._sld_pos.sliderMoved.connect(self._player.setPosition)
        self._sld_pos.sliderReleased.connect(
            lambda: self._player.setPosition(self._sld_pos.value()))
        self._sld_vol.valueChanged.connect(
            lambda v: self._audio.setVolume(v / 100.0))
        self._player.errorOccurred.connect(self._on_media_error)
        self._player.setLoops(-1)  # 循环播放，更像“广告”
        self._player.play()
        self._loaded = True

    # ---------- 视频控制 ----------
    def _toggle_play(self):
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_play_state(self, st):
        if getattr(self, "_btn_play", None) is not None:
            self._btn_play.setText(
                "⏸" if st == QMediaPlayer.PlayingState else "▶")

    def _on_pos(self, pos):
        if getattr(self, "_sld_pos", None) is not None and not self._sld_pos.isSliderDown():
            self._sld_pos.setValue(int(pos))
        if self._player is not None:
            self._upd_time(self._player.duration(), pos)

    def _upd_time(self, dur, pos):
        if getattr(self, "_lbl_time", None) is not None:
            self._lbl_time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(dur)}")

    def _on_media_error(self, err, err_str):
        """视频无法解码/文件损坏 → 显示错误提示页。"""
        page = QLabel(
            f"视频无法播放：{err_str or '格式不受支持'}\n"
            "建议使用 MP4（H.264 编码）视频文件。"
        )
        page.setAlignment(Qt.AlignCenter)
        page.setWordWrap(True)
        page.setStyleSheet(
            "background:#202020; color:#eee; font-size:13px; padding:20px;")
        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)

    # ---------- 焦点策略 ----------
    def _make_interactive(self):
        """加载网页/视频后：移除 WS_EX_NOACTIVATE 并主动激活窗口，
        让 QWebEngineView 真正获得鼠标/键盘输入（点击链接可跳转）。
        代价是激活弹窗会切走 WPS 前台（摸鱼打字本就只在 WPS 前台时进行，
        关闭弹窗后回到 WPS 即继续）。"""
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                (style & ~WS_EX_NOACTIVATE) | WS_EX_TOPMOST,
            )
        except Exception:
            pass
        self._interactive = True
        # 主动把窗口提到前台、取得输入焦点（WebEngine 交互的前提）
        try:
            user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
            user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass
        self.raise_()
        self.activateWindow()

    # ---------- 显示 / 关闭 ----------
    def reveal(self):
        """弹出：屏幕右下角（任务栏上方），不抢焦点。"""
        try:
            scr = QApplication.primaryScreen()
            if scr is not None:
                g = scr.availableGeometry()
                self.move(g.right() - self.width() - 24,
                          g.bottom() - self.height() - 24)
        except Exception:
            pass
        self.show()
        self.raise_()
        if not self._interactive:
            self._apply_noactivate()

    def _apply_noactivate(self):
        """加 WS_EX_NOACTIVATE：弹出/点击都不抢 WPS 前台（默认广告图模式）。"""
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
            )
        except Exception:
            pass

    def shutdown(self):
        """停止播放并关闭弹窗。"""
        try:
            if self._player is not None:
                self._player.stop()
        except Exception:
            pass
        self._player = None
        self._audio = None
        self.close()
        self.deleteLater()

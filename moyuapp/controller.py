# -*- coding: utf-8 -*-
"""摸鱼文书 v2 控制面板（真 WPS 驱动模式）。

软件拉起真实 WPS，把你导入的文章逐字“打”进真实 WPS 窗口——
因为跑的就是真 WPS，界面 100% 真实，且最终白得一份真文档。

控制面板只负责：导入文件、显示进度/目录、开始/暂停/停止、
按键节奏、失焦拉回 WPS、皮肤、版权声明、进度保存。
真正的“打字”由 wps_driver + keyboard_hook 在后台完成。
"""

import os
import sys
import json
import re
from collections import deque

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QListWidget, QFileDialog,
    QTextEdit, QSlider, QCheckBox, QMessageBox, QSystemTrayIcon, QMenu,
    QInputDialog, QSpinBox, QComboBox, QLineEdit, QDialog,
)
from PySide6.QtCore import Qt, QTimer, QSize, QUrl
from PySide6.QtGui import QIcon, QAction, QPixmap, QFontDatabase, QDesktopServices

from . import docimport
from . import wps_driver
from . import keyboard_hook
from . import gongwen
from . import ad_popup
from . import __version__, __build__, __copyright__, __license_note__, __app_name__


# ============ 外观（亮/暗）============
DARK_QSS = """
QWidget { background:#1e1f22; color:#e6e6e6; font-family:'Microsoft YaHei UI'; font-size:13px; }
QPushButton { background:#2b2d31; border:1px solid #3a3d42; border-radius:6px; padding:6px 12px; }
QPushButton:hover { background:#36383d; }
QPushButton:disabled { color:#666; }
QListWidget, QTextEdit { background:#26282c; border:1px solid #3a3d42; border-radius:6px; }
QProgressBar { border:1px solid #3a3d42; border-radius:4px; text-align:center; }
QProgressBar::chunk { background:#c8452c; }
QLabel#Title { font-size:16px; font-weight:bold; color:#f0c674; }
QLabel#Status { color:#8ec07c; }
QSlider::groove:horizontal { background:#3a3d42; height:4px; border-radius:2px; }
QSlider::handle:horizontal { background:#c8452c; width:14px; border-radius:7px; }
"""

LIGHT_QSS = """
QWidget { background:#f5f6f7; color:#222; font-family:'Microsoft YaHei UI'; font-size:13px; }
QPushButton { background:#ffffff; border:1px solid #d0d3d6; border-radius:6px; padding:6px 12px; }
QPushButton:hover { background:#eef0f2; }
QPushButton:disabled { color:#aaa; }
QListWidget, QTextEdit { background:#ffffff; border:1px solid #d0d3d6; border-radius:6px; }
QProgressBar { border:1px solid #d0d3d6; border-radius:4px; text-align:center; }
QProgressBar::chunk { background:#c8452c; }
QLabel#Title { font-size:16px; font-weight:bold; color:#b03a26; }
QLabel#Status { color:#2e7d32; }
QSlider::groove:horizontal { background:#d0d3d6; height:4px; border-radius:2px; }
QSlider::handle:horizontal { background:#c8452c; width:14px; border-radius:7px; }
"""


def _appdata_dir():
    d = os.path.join(os.path.expandvars("%APPDATA%"), "摸鱼文书")
    os.makedirs(d, exist_ok=True)
    return d


def _res_path(*parts):
    """返回打包资源路径：冻结后从 _MEIPASS 取，开发态从项目根取。"""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, *parts)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


def _app_icon():
    p = _res_path("assets", "icon.ico")
    return QIcon(p) if os.path.exists(p) else QIcon()


# 手动按键模式下直接放行的“编辑/导航键”：不产字、不能当打字驱动，
# 放行后用户可在 WPS 里真实删除（退格/Delete）、移动光标修改内容。
_EDIT_PASS_VKS = {
    0x08,        # VK_BACK（退格）
    0x2E,        # VK_DELETE
    0x25, 0x26, 0x27, 0x28,  # ← ↑ → ↓
    0x21, 0x22,  # PgUp / PgDn
    0x23, 0x24,  # End / Home
}


class ControllerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}  (build {__build__})")
        self.setWindowIcon(_app_icon())
        self.resize(420, 730)

        self._driver = wps_driver.WpsDriver()
        self._hook = keyboard_hook.KeyboardInterceptor()
        self._doc_text = ""
        self._total = 0
        self._index = 0
        self._active = False
        self._queue = deque()
        self._interval_ms = 20
        self._gongwen = False
        self._dark = True
        self._file_path = None
        self._blocks = []
        self._blank_doc = os.path.join(_appdata_dir(), "blank.docx")
        self._gongwen_path = os.path.join(_appdata_dir(), "gongwen.docx")
        self._opened_kind = None   # 当前 WPS 打开的是 'blank' 还是 'gongwen' 模板
        self._opened_file = None   # 当前 WPS 打开文档对应的源文件路径
        self._pending_position = False  # 公文模式：需把光标定位到 _index 对应段落

        # 假弹窗广告配置（v2.0.7：延迟改按秒计，最低 10 秒）
        self._ad_enabled = False
        self._ad_delay_sec = 300   # 开始摸鱼后多少秒弹出（最低 10）
        self._ad_mode = "image"    # image | url | video
        self._ad_url = ""          # 网页 URL 或视频路径（按 _ad_mode 解释）
        self._ad_popup = None
        self._ad_timer = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.setInterval(self._interval_ms)
        self._timer.start()

        self._build_ui()
        self._apply_skin()
        self._load_config()

        # 系统托盘
        self._build_tray()

        self._set_status("未开始（请先导入文档，再点开始）")

    # ===================== UI =====================
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        self.lbl_title = QLabel(f"{__app_name__} · 真 WPS 摸鱼")
        self.lbl_title.setObjectName("Title")
        v.addWidget(self.lbl_title)

        self.lbl_status = QLabel("未开始")
        self.lbl_status.setObjectName("Status")
        v.addWidget(self.lbl_status)

        h = QHBoxLayout()
        self.btn_import = QPushButton("导入文档")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_start = QPushButton("开始摸鱼")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause = QPushButton("暂停")
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_pause.setEnabled(False)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        self.btn_skin = QPushButton("皮肤:暗")
        self.btn_skin.clicked.connect(self._on_skin)
        self.btn_about = QPushButton("关于")
        self.btn_about.clicked.connect(self._on_about)
        h.addWidget(self.btn_import)
        h.addWidget(self.btn_start)
        h.addWidget(self.btn_pause)
        h.addWidget(self.btn_stop)
        v.addLayout(h)

        h2 = QHBoxLayout()
        h2.addWidget(self.btn_skin)
        h2.addWidget(self.btn_about)
        v.addLayout(h2)

        self.lbl_file = QLabel("当前文件：无")
        self.lbl_file.setWordWrap(True)
        v.addWidget(self.lbl_file)

        self.lbl_progress = QLabel("进度：0 / 0 字 (0%)")
        v.addWidget(self.lbl_progress)

        self.bar = QProgressBar()
        self.bar.setValue(0)
        v.addWidget(self.bar)

        # 进度控制：重置 / 自定义
        hprog = QHBoxLayout()
        self.btn_reset_progress = QPushButton("重置进度")
        self.btn_reset_progress.clicked.connect(self._on_reset_progress)
        self.btn_custom_progress = QPushButton("自定义进度")
        self.btn_custom_progress.clicked.connect(self._on_custom_progress)
        hprog.addWidget(self.btn_reset_progress)
        hprog.addWidget(self.btn_custom_progress)
        v.addLayout(hprog)

        # 节奏滑块
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("每字间隔:"))
        self.sld_speed = QSlider(Qt.Horizontal)
        self.sld_speed.setRange(0, 100)
        self.sld_speed.setValue(self._interval_ms)
        self.sld_speed.valueChanged.connect(self._on_speed)
        self.lbl_speed = QLabel(f"{self._interval_ms}ms")
        h3.addWidget(self.sld_speed)
        h3.addWidget(self.lbl_speed)
        v.addLayout(h3)

        self.chk_gongwen = QCheckBox("公文排版（按 GB/T 9704-2012 国标样式生成文档）")
        self.chk_gongwen.setChecked(self._gongwen)
        self.chk_gongwen.toggled.connect(self._on_gongwen_toggle)
        v.addWidget(self.chk_gongwen)

        # 假弹窗广告（右下角气氛组）
        v.addWidget(QLabel("假弹窗广告（右下角气氛组）"))
        h_ad1 = QHBoxLayout()
        self.chk_ad = QCheckBox("启用")
        self.chk_ad.setChecked(self._ad_enabled)
        h_ad1.addWidget(self.chk_ad)
        h_ad1.addWidget(QLabel("开始摸鱼后"))
        self.spin_ad_delay = QSpinBox()
        self.spin_ad_delay.setRange(1, 10080)
        self.spin_ad_delay.setValue(5)
        self.spin_ad_delay.setSuffix(" 分钟")
        self.cmb_ad_unit = QComboBox()
        self.cmb_ad_unit.addItems(["分钟", "秒"])
        h_ad1.addWidget(self.spin_ad_delay)
        h_ad1.addWidget(self.cmb_ad_unit)
        h_ad1.addStretch(1)
        v.addLayout(h_ad1)
        # 初始按内部秒数回填 UI（分钟优先显示整分钟）
        if self._ad_delay_sec % 60 == 0:
            self.spin_ad_delay.setValue(max(1, self._ad_delay_sec // 60))
            self.cmb_ad_unit.setCurrentIndex(0)
            self.spin_ad_delay.setSuffix(" 分钟")
        else:
            self.spin_ad_delay.setValue(max(10, self._ad_delay_sec))
            self.cmb_ad_unit.setCurrentIndex(1)
            self.spin_ad_delay.setSuffix(" 秒")
        h_ad2 = QHBoxLayout()
        self.cmb_ad_mode = QComboBox()
        self.cmb_ad_mode.addItems(["默认广告图", "网页", "本地视频"])
        h_ad2.addWidget(self.cmb_ad_mode)
        self.edt_ad_url = QLineEdit()
        self.edt_ad_url.setPlaceholderText("网页 URL / 视频文件路径")
        h_ad2.addWidget(self.edt_ad_url, 1)
        self.btn_ad_browse = QPushButton("…")
        self.btn_ad_browse.setFixedWidth(32)
        self.btn_ad_browse.setToolTip("选择视频文件或输入网页地址")
        self.btn_ad_browse.clicked.connect(self._on_ad_browse)
        h_ad2.addWidget(self.btn_ad_browse)
        v.addLayout(h_ad2)
        self.chk_ad.toggled.connect(self._sync_ad_from_ui)
        self.spin_ad_delay.valueChanged.connect(self._sync_ad_from_ui)
        self.cmb_ad_unit.currentIndexChanged.connect(self._on_ad_unit_change)
        self.cmb_ad_mode.currentIndexChanged.connect(self._sync_ad_from_ui)
        self.edt_ad_url.textChanged.connect(self._sync_ad_from_ui)
        self._apply_ad_mode_enabled()

        v.addWidget(QLabel("自动目录（按文档结构识别）"))
        self.lst_outline = QListWidget()
        self.lst_outline.setMaximumHeight(160)
        v.addWidget(self.lst_outline)

        v.addWidget(QLabel("运行日志"))
        self.txt_log = QTextEdit()
        self.txt_log.setMaximumHeight(120)
        self.txt_log.setReadOnly(True)
        v.addWidget(self.txt_log)

        self.lbl_tip = QLabel("提示：在 WPS 里按任意键即逐字“打”入文章——关闭输入法为按键摸鱼，"
                              "打开输入法可随时手动打字；退格/删除/方向键真实生效。"
                              "F9 暂停/继续，Ctrl+S 直接保存。")
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setStyleSheet("color:#888;")
        v.addWidget(self.lbl_tip)

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = _app_icon()
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        a_show = QAction("显示面板", self)
        a_show.triggered.connect(self.showNormal)
        a_start = QAction("开始/继续 (F9)", self)
        a_start.triggered.connect(self._on_start)
        a_pause = QAction("暂停", self)
        a_pause.triggered.connect(self._on_pause)
        a_stop = QAction("停止", self)
        a_stop.triggered.connect(self._on_stop)
        a_quit = QAction("退出", self)
        a_quit.triggered.connect(self._confirm_quit)
        menu.addAction(a_show)
        menu.addAction(a_start)
        menu.addAction(a_pause)
        menu.addAction(a_stop)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.showNormal() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def _tray_icon(self):
        return _app_icon()

    # ===================== 皮肤 =====================
    def _apply_skin(self):
        qss = DARK_QSS if self._dark else LIGHT_QSS
        QApplication.instance().setStyleSheet(qss)
        self.btn_skin.setText("皮肤:" + ("暗" if self._dark else "亮"))

    def _on_skin(self):
        self._dark = not self._dark
        self._apply_skin()
        self._save_config()

    # ===================== 导入 =====================
    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入文档", "", "文档 (*.docx *.txt *.pdf)"
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path):
        try:
            blocks = docimport.import_file(path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法解析文件：{e}")
            return
        if not blocks:
            QMessageBox.warning(self, "导入失败", "文件中没有可识别的正文内容。")
            return
        self._file_path = path
        self._blocks = blocks
        self._doc_text = "\n".join(b["text"] for b in blocks)
        self._total = len(self._doc_text)
        self._build_outline(blocks)
        self.lbl_file.setText(f"当前文件：{os.path.basename(path)}\n（{self._total} 字）")

        # 同文件则恢复进度
        saved = self._load_progress()
        if saved and saved.get("file") == path and saved.get("index", 0) <= self._total:
            self._index = saved["index"]
        else:
            self._index = 0
        self._update_progress()
        self._log(f"已导入：{os.path.basename(path)}，共 {self._total} 字，目录 {self.lst_outline.count()} 条。")

    def _build_outline(self, blocks):
        self.lst_outline.clear()
        for b in blocks:
            lvl = b.get("level", 0)
            if lvl < 0:
                indent = 0
            else:
                indent = max(0, lvl - 1)
            prefix = "    " * indent
            self.lst_outline.addItem(f"{prefix}{b['text']}")

    # ===================== 控制 =====================
    def _ensure_hook(self):
        if not self._hook.is_active():
            self._hook.start(self._on_key)

    def _on_start(self):
        if not self._doc_text:
            QMessageBox.information(self, "提示", "请先导入一份 docx 或 txt 文档。")
            return
        if self._index >= self._total:
            self._index = 0  # 已完成则重头开始

        want = "gongwen" if self._gongwen else "blank"
        need_launch = (not self._driver.is_alive()) or (self._opened_kind != want) \
            or (self._opened_file != self._file_path)
        if need_launch:
            if want == "gongwen":
                # 生成本机字体回退的国标模板，每段一个空样式段落
                try:
                    self._build_gongwen_template()
                except Exception as e:
                    QMessageBox.warning(self, "公文模板生成失败", str(e))
                    return
                target = self._gongwen_path
            else:
                target = self._blank_doc
            # 切换模板需重新拉起 WPS；重置进度从头开始
            self._driver = wps_driver.WpsDriver()
            ok, msg = self._driver.launch(target)
            if not ok:
                QMessageBox.warning(self, "无法启动 WPS", msg)
                return
            self._opened_kind = want
            self._opened_file = self._file_path
            if want == "gongwen":
                # 公文模板每段是独立空样式段落：保留 _index（导入默认 0；
                # 若用户此前设过“自定义进度”，则跳到对应段落，前面段落留空，
                # 符合“跳进度”语义），并把光标重定位到对应段落段首。
                self._pending_position = True
            else:
                # 空白文档无段落结构映射，从头打
                self._index = 0
                self._pending_position = False

        self._ensure_hook()
        self._active = True
        self._set_status("摸鱼中（在 WPS 里按键即逐字打入）")
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self._log("已开始：WPS 已拉起。在 WPS 里按任意键“打字”——关闭输入法为按键摸鱼，"
                  "打开输入法可手动打字；退格/删除/方向键真实生效。F9 暂停。")
        # 不隐藏面板：保持可见以便观察进度（WPS 已在前台，面板在其后）。
        if hasattr(self, "tray"):
            self.tray.showMessage(__app_name__, "摸鱼中：在 WPS 里按任意键逐字打入，F9 暂停。", QSystemTrayIcon.Information, 2000)
        # 假弹窗广告定时
        self._arm_ad_timer()

    def _on_pause(self):
        if not self._active:
            return
        self._active = False
        self._queue.clear()
        self._close_ad()
        self._set_status("已暂停")
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self._save_progress()
        self._log("已暂停。")
        self.showNormal()

    def _on_stop(self):
        self._active = False
        self._queue.clear()
        self._close_ad()
        self._set_status("已停止")
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self._save_progress()
        self._log("已停止。WPS 仍保持打开，可手动保存你“写”出来的文档。")
        self.showNormal()

    def _toggle(self):
        if self._active:
            self._on_pause()
        else:
            self._on_start()

    # ===================== 公文排版 / 进度控制 =====================
    def _on_gongwen_toggle(self, b):
        self._gongwen = bool(b)
        self._save_config()
        if self._active:
            # 切换排版模式需要换模板，自动停止当前任务，下次开始用新模板
            self._log("已切换“公文排版”开关，将在下次开始时套用对应模板（已自动停止当前任务）。")
            self._on_stop()

    def _build_gongwen_template(self):
        """按 GB/T 9704-2012 生成本机字体回退的国标空白模板（每段一个空样式段落）。"""
        try:
            families = QFontDatabase.families()
        except Exception:
            families = None
        gongwen.build_docx(self._gongwen_path, self._blocks, families)

    def _position_cursor_to_index(self):
        """公文模式：把 WPS 光标定位到 _index 对应的段落段首。"""
        if not self._gongwen:
            return
        target = self._doc_text.count("\n", 0, self._index)  # 块间换行数 = 段落偏移
        self._driver.goto_doc_start()  # Ctrl+Home → 文档最前
        for _ in range(target):
            self._driver.goto_next_paragraph()

    def _on_reset_progress(self):
        if self._total == 0:
            QMessageBox.information(self, "提示", "请先导入文档再重置进度。")
            return
        r = QMessageBox.question(
            self, "重置进度",
            "确认把进度重置到第 0 字？\n（已“写”进 WPS 的内容不会被自动清除；"
            "如需从空白页重来，请先「停止」再开始。）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self._index = 0
        self._update_progress()
        self._save_progress()
        self._pending_position = self._gongwen
        self._log("进度已重置到第 0 字。")

    def _on_custom_progress(self):
        if self._total == 0:
            QMessageBox.information(self, "提示", "请先导入文档再设置进度。")
            return
        cur, ok = QInputDialog.getInt(
            self, "自定义进度",
            f"跳转到第几个字（0 ~ {self._total}）：",
            self._index, 0, self._total, 1,
        )
        if not ok:
            return
        self._index = cur
        self._update_progress()
        self._save_progress()
        # 公文模式：下次开始 / 切回 WPS 前台时把光标定位到对应段落
        self._pending_position = self._gongwen
        self._log(f"进度已跳转到第 {cur} 字（公文模式下将定位到对应段落）。")

    # ===================== 假弹窗广告 =====================
    def _sync_ad_from_ui(self, *_):
        self._ad_enabled = self.chk_ad.isChecked()
        unit = self.cmb_ad_unit.currentIndex()  # 0=分钟 1=秒
        self._ad_delay_sec = self.spin_ad_delay.value() * (60 if unit == 0 else 1)
        self._ad_mode = ("image", "url", "video")[self.cmb_ad_mode.currentIndex()]
        self._ad_url = self.edt_ad_url.text().strip()
        self._apply_ad_mode_enabled()
        self._save_config()

    def _on_ad_unit_change(self):
        """切换 分钟/秒：换后缀并换算数值（秒最低 10）。"""
        old_unit = 1 if self.spin_ad_delay.suffix() == " 秒" else 0
        new_unit = self.cmb_ad_unit.currentIndex()
        val = self.spin_ad_delay.value()
        self.spin_ad_delay.blockSignals(True)
        if new_unit == 1 and old_unit == 0:      # 分钟 → 秒
            self.spin_ad_delay.setSuffix(" 秒")
            self.spin_ad_delay.setValue(max(10, val * 60))
        elif new_unit == 0 and old_unit == 1:    # 秒 → 分钟
            self.spin_ad_delay.setSuffix(" 分钟")
            self.spin_ad_delay.setValue(max(1, round(val / 60)))
        else:
            self.spin_ad_delay.setSuffix(" 秒" if new_unit == 1 else " 分钟")
        self.spin_ad_delay.blockSignals(False)
        self._sync_ad_from_ui()

    def _apply_ad_mode_enabled(self):
        self.edt_ad_url.setEnabled(self.cmb_ad_mode.currentIndex() != 0)
        self.btn_ad_browse.setEnabled(self.cmb_ad_mode.currentIndex() != 0)

    def _on_ad_browse(self):
        if self.cmb_ad_mode.currentIndex() == 1:  # 网页
            url, ok = QInputDialog.getText(
                self, "网页地址", "输入弹窗加载的网页 URL：",
                text=self._ad_url or "https://",
            )
            if ok and url.strip():
                self.edt_ad_url.setText(url.strip())
        else:  # 本地视频
            path, _ = QFileDialog.getOpenFileName(
                self, "选择本地视频", "",
                "视频 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv);;所有文件 (*)",
            )
            if path:
                self.edt_ad_url.setText(path)

    def _arm_ad_timer(self):
        """开始摸鱼时按配置安排“假广告”定时弹出（最低 10 秒）。"""
        self._disarm_ad_timer()
        if self._ad_enabled and self._ad_delay_sec >= 10:
            self._ad_timer = QTimer(self)
            self._ad_timer.setSingleShot(True)
            self._ad_timer.setInterval(self._ad_delay_sec * 1000)
            self._ad_timer.timeout.connect(self._show_ad)
            self._ad_timer.start()

    def _disarm_ad_timer(self):
        if self._ad_timer is not None:
            try:
                self._ad_timer.stop()
            except Exception:
                pass
            self._ad_timer = None

    def _show_ad(self):
        try:
            self._close_ad()
            p = ad_popup.AdPopup(
                self._ad_mode,
                self._ad_url if self._ad_mode == "url" else "",
                self._ad_url if self._ad_mode == "video" else "",
            )
            self._ad_popup = p
            p.reveal()
            self._log("假弹窗广告已弹出（右下角），点击“×”关闭。")
        except Exception as e:
            self._log(f"假弹窗广告弹出失败：{e}")

    def _close_ad(self):
        self._disarm_ad_timer()
        if self._ad_popup is not None:
            try:
                self._ad_popup.shutdown()
            except Exception:
                pass
            self._ad_popup = None

    # ===================== 键盘钩子回调 =====================
    def _on_key(self, vk, flags):
        # 自己用 SendInput 注入的事件标志位为 LLKHF_INJECTED(0x10)，必须放行，
        # 否则会把自己的字又吞掉、永远到不了 WPS。
        if flags & keyboard_hook.LLKHF_INJECTED:
            return False
        # 修饰键 / 系统组合键放行（保证 Ctrl+S 保存、Alt+Tab 切换等可用）
        if vk in keyboard_hook._MODIFIER_VKS:
            return False
        if keyboard_hook.modifier_held():
            return False
        # F9 切换开始/暂停
        if vk == 0x78:
            QTimer.singleShot(0, self._toggle)
            return True
        if not self._active:
            return False
        if not self._driver or not self._driver.pid:
            return False
        # 按键驱动模式：WPS 前台时吞键并入队一个字
        if self._driver.is_foreground():
            # 编辑/导航键放行：退格/Delete/方向/Home/End 不产字、不能当打字驱动，
            # 放行后可直接在 WPS 里真实删字、移动光标（修复 v2.0.5 删除无效）。
            if vk in _EDIT_PASS_VKS:
                return False
            # 输入法处于“打开”状态（中文模式）时整体放行：
            # 用户可随时用中文输入法手动打字/修改（修复 v2.0.5 手动模式输入法无效）。
            # 关闭输入法（英文态）即恢复“按键摸鱼”驱动。
            try:
                if self._driver.ime_open_for_window():
                    return False
            except Exception:
                pass
            self._queue.append(1)
            return True
        return False

    # ===================== 抽干队列，逐字打入 WPS =====================
    def _drain(self):
        if not self._active:
            return
        # 公文模式：先把光标定位到 _index 对应段落（自定义进度/换模板后）
        if self._gongwen and self._pending_position:
            fg = bool(self._driver and self._driver.is_alive()
                      and self._driver.is_foreground())
            if fg:
                self._position_cursor_to_index()
                self._pending_position = False
        # 按键驱动：由钩子入队，每个键打一个字
        if not self._queue:
            return
        if not (self._driver and self._driver.pid):
            self._queue.clear()
            return
        if not self._driver.is_foreground():
            self._queue.clear()
            return
        self._queue.popleft()
        self._reveal_one()

    def _reveal_one(self):
        if self._index >= self._total:
            self._finish()
            return
        ch = self._doc_text[self._index]
        # 公文排版：模板每段已是一个独立的空“样式段落”，
        # 块之间的换行不插段落符，而是直接跳到下一段落继续打。
        if self._gongwen and ch == "\n":
            try:
                self._driver.goto_next_paragraph()
            except Exception as e:
                self._log(f"段落跳转失败：{e}")
            self._index += 1
            self._update_progress()
            if self._index % 25 == 0:
                self._save_progress()
            return
        try:
            ok = self._driver.type_char(ch)
        except Exception as e:
            self._log(f"发送失败：{e}")
            ok = False
        if not ok:
            self._log("向 WPS 发送失败，可能窗口已关闭。已自动暂停。")
            if hasattr(self, "tray"):
                self.tray.showMessage(__app_name__, "向 WPS 发送失败，已暂停。", QSystemTrayIcon.Critical, 2000)
            self._on_pause()
            return
        self._index += 1
        self._update_progress()
        if self._index % 25 == 0:
            self._save_progress()

    def _finish(self):
        self._active = False
        self._queue.clear()
        self._close_ad()
        self._set_status("已完成")
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self._save_progress()
        self._log("文档已全部“打”完。WPS 里的就是成品，记得 Ctrl+S 保存。")
        self.showNormal()
        if hasattr(self, "tray"):
            self.tray.showMessage(__app_name__, "文档已写完！", QSystemTrayIcon.Information, 2000)

    def _update_progress(self):
        pct = int(self._index / self._total * 100) if self._total else 0
        self.bar.setValue(pct)
        self.lbl_progress.setText(f"进度：{self._index} / {self._total} 字 ({pct}%)")

    # ===================== 配置 / 进度 =====================
    def _load_config(self):
        cfg = os.path.join(_appdata_dir(), "config.json")
        if os.path.exists(cfg):
            try:
                d = json.load(open(cfg, "r", encoding="utf-8"))
                self._dark = d.get("dark", True)
                self._interval_ms = d.get("interval", 20)
                self._gongwen = d.get("gongwen", False)
                self._ad_enabled = d.get("ad_enabled", False)
                # v2.0.7 起延迟按秒存（最低 10 秒）；兼容旧版“分钟”配置
                if "ad_delay_sec" in d:
                    self._ad_delay_sec = int(d.get("ad_delay_sec", 300))
                else:
                    self._ad_delay_sec = max(10, int(d.get("ad_delay_min", 5)) * 60)
                self._ad_mode = d.get("ad_mode", "image")
                self._ad_url = d.get("ad_url", "")
                self.sld_speed.setValue(self._interval_ms)
                self.lbl_speed.setText(f"{self._interval_ms}ms")
                if hasattr(self, "chk_gongwen"):
                    self.chk_gongwen.setChecked(self._gongwen)
                if hasattr(self, "chk_ad"):
                    # blockSignals：防止 setChecked/setValue 触发 _sync_ad_from_ui
                    # 用控件当前值把刚读入的配置覆盖掉
                    ad_widgets = (self.chk_ad, self.spin_ad_delay,
                                  self.cmb_ad_unit, self.cmb_ad_mode, self.edt_ad_url)
                    for w in ad_widgets:
                        w.blockSignals(True)
                    self.chk_ad.setChecked(self._ad_enabled)
                    if self._ad_delay_sec % 60 == 0:
                        self.spin_ad_delay.setValue(max(1, self._ad_delay_sec // 60))
                        self.spin_ad_delay.setSuffix(" 分钟")
                        self.cmb_ad_unit.setCurrentIndex(0)
                    else:
                        self.spin_ad_delay.setValue(max(10, self._ad_delay_sec))
                        self.spin_ad_delay.setSuffix(" 秒")
                        self.cmb_ad_unit.setCurrentIndex(1)
                    self.cmb_ad_mode.setCurrentIndex(
                        {"image": 0, "url": 1, "video": 2}.get(self._ad_mode, 0))
                    self.edt_ad_url.setText(self._ad_url)
                    for w in ad_widgets:
                        w.blockSignals(False)
                    self._apply_ad_mode_enabled()
            except Exception:
                pass

    def _save_config(self):
        cfg = os.path.join(_appdata_dir(), "config.json")
        try:
            json.dump({
                "dark": self._dark,
                "interval": self._interval_ms,
                "gongwen": self._gongwen,
                "ad_enabled": self._ad_enabled,
                "ad_delay_sec": self._ad_delay_sec,
                "ad_mode": self._ad_mode,
                "ad_url": self._ad_url,
            }, open(cfg, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass

    def _load_progress(self):
        p = os.path.join(_appdata_dir(), "progress.json")
        if os.path.exists(p):
            try:
                return json.load(open(p, "r", encoding="utf-8"))
            except Exception:
                return None
        return None

    def _save_progress(self):
        p = os.path.join(_appdata_dir(), "progress.json")
        try:
            json.dump({
                "file": self._file_path,
                "index": self._index,
            }, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass

    # ===================== 杂项 =====================
    def _set_status(self, text):
        self.lbl_status.setText(text)

    def _log(self, msg):
        self.txt_log.append(msg)

    def _on_speed(self, val):
        self._interval_ms = val
        self._timer.setInterval(max(1, val))
        self.lbl_speed.setText(f"{val}ms")
        self._save_config()

    # 联系作者（关于对话框展示，图标在 assets/）
    _CONTACTS = [
        ("icon_github.png", "GitHub", "https://github.com/zouzuo1994321"),
        ("icon_bilibili.png", "哔哩哔哩", "https://space.bilibili.com/13715"),
        ("icon_weibo.png", "微博", "https://weibo.com/u/5189652182"),
        ("icon_email.png", "邮箱 921103025@qq.com", "mailto:921103025@qq.com"),
    ]

    def _on_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("关于 " + __app_name__)
        dlg.setFixedWidth(380)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(24, 20, 24, 16)
        v.setSpacing(10)

        title = QLabel(f"{__app_name__} {__version__}")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#f0c674; background:transparent;")
        v.addWidget(title)

        info = QLabel(
            f"build {__build__}<br>{__copyright__}<br>{__license_note__}<br><br>"
            "本软件通过拉起真实 WPS 并在后台逐字输入，"
            "实现“看起来在认真写文档”的摸鱼效果。"
        )
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        info.setOpenExternalLinks(True)
        v.addWidget(info)

        v.addSpacing(6)
        ct = QLabel("联系作者")
        ct.setStyleSheet("font-weight:bold; background:transparent;")
        v.addWidget(ct)

        for icon_name, label, url in self._CONTACTS:
            row = QHBoxLayout()
            row.setSpacing(10)
            ic = QLabel()
            pm = QPixmap(ad_popup._res_path("assets", icon_name))
            if not pm.isNull():
                ic.setPixmap(pm.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            ic.setFixedSize(32, 32)
            ic.setAlignment(Qt.AlignCenter)
            ic.setStyleSheet(
                "background:#111; border-radius:8px; padding:4px;")
            row.addWidget(ic)
            lnk = QLabel(f'<a href="{url}" style="color:#8ec07c; text-decoration:none;">{label}</a>')
            lnk.setTextInteractionFlags(Qt.TextBrowserInteraction)
            lnk.setOpenExternalLinks(True)
            lnk.setStyleSheet("background:transparent;")
            row.addWidget(lnk)
            row.addStretch(1)
            v.addLayout(row)

        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn, 0, Qt.AlignRight)
        dlg.exec()

    def _confirm_quit(self):
        self._cleanup()
        self._force_kill_later()
        QApplication.instance().quit()

    def _cleanup(self):
        self._active = False
        self._hook.stop()
        self._close_ad()
        try:
            self._timer.stop()          # 打字节奏定时器
        except Exception:
            pass
        try:
            self._disarm_ad_timer()     # 弹窗广告定时器
        except Exception:
            pass
        # 不强制关闭 WPS，保留用户“写”出来的文档
        if getattr(sys, "frozen", False):
            # 冻结运行时由 main 负责 ensure_exit，这里仅做清理
            pass

    def _force_kill_later(self):
        """兜底：若 1.5 秒后事件循环仍未退出（如 WebEngine 线程阻塞），
        直接杀死自身进程，保证关闭软件后绝不残留。"""
        QTimer.singleShot(1500, lambda: os._exit(0))

    def closeEvent(self, event):
        # 关闭即退出（不再隐藏到托盘），并主动杀死进程
        self._cleanup()
        event.accept()
        self._force_kill_later()
        QApplication.instance().quit()

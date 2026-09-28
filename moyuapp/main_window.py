# -*- coding: utf-8 -*-
"""摸鱼文书主窗口 —— 高仿 WPS 界面 + 摸鱼逐字输入 + 公文排版。

Copyright 2026 肆月Aperture
本软件为开源软件，没有授权禁止用于商业用途。
"""

import json
import os
import sys
import time

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QEvent, QSize
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPixmap, QTextCharFormat, QTextCursor,
                           QTextBlockFormat, QInputMethodEvent, QPainter, QPen)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QStatusBar, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from . import __version__, __build__, __app_name__, __copyright__, __license_note__
from . import docimport, govstyle
from .themes import THEMES

SESSION_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MoyuDocs")
SESSION_FILE = os.path.join(SESSION_DIR, "last_session.json")

ACCENT = "#c8452c"  # WPS 红


def _asset(name: str) -> str:
    """定位 assets/ 资源。冻结运行时**优先读 exe 旁边的 assets/**
    （用户可直接替换图片立即生效），不存在才回退到 PyInstaller 解包目录。"""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        local = os.path.join(exe_dir, "assets", name)
        if os.path.exists(local):
            return local
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.exists(os.path.join(meipass, "assets", name)):
            return os.path.join(meipass, "assets", name)
        return local
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", name)


# ---------------------------------------------------------------------------
# 纸张（摸鱼输入核心）
# ---------------------------------------------------------------------------
class Paper(QTextEdit):
    """A4 公文纸张。任意按键（含输入法提交） = 文章下一个字出现；退格删字；
    撤回/重做基于快照栈；实际内容不影响（摸鱼模式，无需核对键入内容）。"""

    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Paper")
        # 关键：不能 readOnly，否则输入法根本不会把合成/提交事件发给本控件；
        # 改为“可编辑 + 全拦截”，真实键入永远不会写进文档，只有文章出字。
        self.setReadOnly(False)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setAcceptDrops(False)
        self.setCursorWidth(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAcceptRichText(False)
        self.on_change = on_change or (lambda: None)
        self.blocks = []
        self.revealed = []
        self.undo_stack = []
        self.redo_stack = []
        self._render_lock = False

    # ---- 基础 ----
    def load_blocks(self, blocks, revealed=None):
        self.blocks = [dict(b) for b in blocks]
        n = len(self.blocks)
        self.revealed = list(revealed) if revealed and len(revealed) == n else [0] * n
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.full_render()
        self.on_change()

    def total_chars(self):
        return sum(len(b["text"]) for b in self.blocks)

    def shown_chars(self):
        return sum(self.revealed)

    def is_empty_doc(self):
        doc = self.document()
        return doc.blockCount() <= 1 and doc.firstBlock().length() <= 1

    # ---- 渲染 ----
    def _insert_block_text(self, cursor, bi):
        b = self.blocks[bi]
        if self.revealed[bi] <= 0:
            return
        cursor.insertBlock(govstyle.block_format_for_level(b["level"]))
        cf = govstyle.char_format_for_level(b["level"])
        cursor.insertText(b["text"][: self.revealed[bi]], cf)

    def full_render(self):
        """按 revealed 状态重建整篇文档（导入/撤回/重做/换肤用）。"""
        self._render_lock = True
        sb = self.verticalScrollBar().value()
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.removeSelectedText()
        cursor = self.textCursor()
        for bi in range(len(self.blocks)):
            self._insert_block_text(cursor, bi)
        doc = self.document()
        if doc.blockCount() > 1 and doc.firstBlock().length() <= 1:
            c = QTextCursor(doc.firstBlock())
            c.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            c.removeSelectedText()
        self.verticalScrollBar().setValue(sb)
        self._render_lock = False

    # ---- 摸鱼输入 ----
    def reveal_next(self):
        if self._render_lock or not self.blocks:
            return False
        bi = None
        for i in range(len(self.blocks)):
            if self.revealed[i] < len(self.blocks[i]["text"]):
                bi = i
                break
        if bi is None:
            return False
        self._push_undo()
        self.revealed[bi] += 1
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self.revealed[bi] == 1:
            if not self.is_empty_doc():
                cursor.insertBlock(govstyle.block_format_for_level(self.blocks[bi]["level"]))
            else:
                cursor.setBlockFormat(govstyle.block_format_for_level(self.blocks[bi]["level"]))
        cursor.insertText(self.blocks[bi]["text"][self.revealed[bi] - 1],
                          govstyle.char_format_for_level(self.blocks[bi]["level"]))
        self._scroll_to_bottom()
        self.on_change()
        return True

    def reveal_back(self):
        if self._render_lock or not self.blocks:
            return False
        bi = None
        for i in range(len(self.blocks) - 1, -1, -1):
            if self.revealed[i] > 0:
                bi = i
                break
        if bi is None:
            return False
        self._push_undo()
        self.revealed[bi] -= 1
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.deletePreviousChar()
        if self.revealed[bi] == 0 and self.document().blockCount() > 1:
            cursor.deletePreviousChar()
        self.on_change()
        return True

    def _push_undo(self):
        self.undo_stack.append(list(self.revealed))
        if len(self.undo_stack) > 300:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(list(self.revealed))
        self.revealed = self.undo_stack.pop()
        self.full_render()
        self.on_change()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(list(self.revealed))
        self.revealed = self.redo_stack.pop()
        self.full_render()
        self.on_change()
        return True

    def _scroll_to_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def scroll_to_block(self, seq_index):
        seq = [i for i in range(len(self.blocks)) if self.revealed[i] > 0]
        if seq_index >= len(seq):
            return
        doc = self.document()
        blk = doc.firstBlock()
        for _ in range(seq_index):
            blk = blk.next()
            if not blk.isValid():
                return
        cur = QTextCursor(blk)
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    # ---- 输入法：支持拼音/手写等提交逐字出字 ----
    def commit_text(self, text: str):
        """处理输入法提交的文本：逐字出字（不核对真实内容）。"""
        if not text:
            return
        for _ in text:
            self.reveal_next()

    def inputMethodEvent(self, event: QInputMethodEvent):
        commit = event.commitString()
        if commit:
            self.commit_text(commit)
        # 合成中的 preedit（拼音上屏）不写入，仅出字；不调用基类 → 真实文本绝不落入文档
        event.accept()

    # ---- 封死一切旁路编辑入口 ----
    def insertFromMimeData(self, source):  # 粘贴
        pass

    def contextMenuEvent(self, ev):  # 右键菜单（含剪切/粘贴）不弹出
        ev.accept()

    # ---- 键盘：摸鱼输入核心 ----
    def keyPressEvent(self, ev):
        mods = ev.modifiers()
        key = ev.key()
        if mods & Qt.ControlModifier:
            if key == Qt.Key_Z:
                (self.redo() if mods & Qt.ShiftModifier else self.undo())
                return
            if key == Qt.Key_Y:
                self.redo()
                return
            if key in (Qt.Key_C, Qt.Key_V, Qt.Key_X, Qt.Key_A):
                return
        if key == Qt.Key_Backspace:
            self.reveal_back()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.reveal_next()
            return
        text = ev.text()
        if text and text.isprintable() and not (mods & (Qt.AltModifier | Qt.ControlModifier)):
            self.reveal_next()
            return
        # 其余（方向键、Delete、F 键等）一律吞掉，防止移动光标/删除内容
        return


# ---------------------------------------------------------------------------
# 水平标尺（提升 WPS 像真度）
# ---------------------------------------------------------------------------
class Ruler(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setObjectName("Ruler")

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setPen(QPen(QColor("#b9b9bf"), 1))
        w = self.width()
        step = 12
        for x in range(0, w, step):
            h = 8 if x % (step * 10) == 0 else (5 if x % (step * 5) == 0 else 3)
            p.drawLine(x, self.height() - h, x, self.height())
        p.end()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.article_path = ""
        self.theme = "dark"
        self.autosave = True
        self._dirty = False
        self._nav_tabs = {}
        self.setWindowTitle(f"{__app_name__} {__version__} Build {__build__}")
        self.resize(1360, 880)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self._drag_pos = None

        self._build_ui()
        self._apply_theme("dark")

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30000)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        central = QWidget(objectName="RootCentral")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_chrome())
        root.addWidget(self._build_function_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_left_panel())
        body.addWidget(self._build_center(), 1)
        body.addWidget(self._build_right_panel())
        root.addLayout(body, 1)

        self.setStatusBar(QStatusBar(objectName="StatusBar"))
        self.statusBar().showMessage(
            f"就绪 · 摸鱼模式：任意输入（支持输入法）出字，退格删字，Ctrl+Z 撤回 · {__copyright__}")
        self.setCentralWidget(central)
        self._update_placeholder()

    def _build_chrome(self):
        """顶部整条（标题栏+菜单+功能区）直接用真实 WPS 截图还原（assets/ribbon_*.png，
        由 assets/build_prep.py 从 截图/ 裁切生成；替换该图片即换肤）。"""
        self._chrome_label = QLabel()
        self._chrome_label.setObjectName("ChromeImage")
        self._chrome_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._set_chrome_image()
        # 截图本身就是标题栏：按住可拖动窗口
        self._chrome_label.mousePressEvent = self._title_press
        self._chrome_label.mouseMoveEvent = self._title_move
        return self._chrome_label

    def _set_chrome_image(self):
        pm = QPixmap(_asset(f"ribbon_{self.theme}.png"))
        if not pm.isNull():
            self._chrome_pm = pm
            self._chrome_label.setPixmap(pm)
            self._chrome_label.setFixedHeight(pm.height())
        else:
            self._chrome_pm = None
            self._chrome_label.setFixedHeight(96)

    def resizeEvent(self, ev):
        """窗口变宽/变窄时，顶部截图 chrome 跟随宽度缩放。"""
        super().resizeEvent(ev)
        if hasattr(self, "_chrome_pm") and self._chrome_pm is not None and hasattr(self, "_chrome_label"):
            self._chrome_label.setPixmap(self._chrome_pm.scaled(
                self.width(), self._chrome_pm.height(),
                Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

    def _title_press(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.windowHandle().startSystemMove()

    def _title_move(self, ev):
        if self._drag_pos is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _build_function_bar(self):
        """唯一真实的按钮区：只保留摸鱼需要的功能。"""
        bar = QWidget(objectName="QuickAccess")
        bar.setFixedHeight(38)
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(4)

        self._file_menu = QMenu(self)
        self._file_menu.addAction("导入文档 (Word / TXT)…", self.open_document)
        self._file_menu.addAction("保存摸鱼进度", self.save_progress)
        self._file_menu.addAction("恢复上次进度", self.restore_last_session)
        self._file_menu.addSeparator()
        self._file_menu.addAction("关于 摸鱼文书", self.show_about)
        self._file_menu.addAction("退出", self.close)

        file_btn = QPushButton("☰ 摸鱼功能")
        file_btn.setObjectName("PrimaryBtn")
        file_btn.clicked.connect(lambda: self._file_menu.exec(self.mapToGlobal(file_btn.pos())))
        h.addWidget(file_btn)

        def icon(text, tip, fn):
            b = QToolButton(text=text, toolTip=tip)
            b.setFixedSize(34, 30)
            b.clicked.connect(fn)
            h.addWidget(b)
            return b

        icon("📂", "导入文档 (Ctrl+O)", self.open_document)
        icon("💾", "保存进度 (Ctrl+S)", self.save_progress)
        icon("↩", "撤回 (Ctrl+Z)", lambda: self.paper.undo())
        icon("↪", "重做 (Ctrl+Y)", lambda: self.paper.redo())

        self.title_doc = QLabel("文字文稿1")
        self.title_doc.setStyleSheet("color:#9aa0a6;")
        h.addWidget(self.title_doc)
        h.addStretch(1)

        self.skin_btn = QPushButton("🌙 深色", objectName="FlatBtn")
        self.skin_btn.clicked.connect(self.toggle_theme)
        h.addWidget(self.skin_btn)
        about_btn = QPushButton("关于", objectName="FlatBtn")
        about_btn.clicked.connect(self.show_about)
        h.addWidget(about_btn)

        for b, fn in ((QToolButton(text="—"), self.showMinimized),
                      (QToolButton(text="□"), self._toggle_max),
                      (QToolButton(text="✕"), self.close)):
            b.setFixedSize(32, 26)
            b.setStyleSheet("QToolButton{color:#bbb;background:transparent;border:none;}"
                            "QToolButton:hover{background:#444;}")
            b.clicked.connect(fn)
            h.addWidget(b)
        return bar

    def _build_left_panel(self):
        panel = QWidget(objectName="LeftPanel")
        panel.setFixedWidth(210)
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        nav = QHBoxLayout()
        nav.setSpacing(2)
        for name in ("目录", "书签", "查找"):
            b = QPushButton(name)
            b.setObjectName("NavTab" + (" Active" if name == "目录" else ""))
            b.clicked.connect(lambda _=False, n=name: self._switch_nav(n))
            nav.addWidget(b)
            self._nav_tabs[name] = b
        v.addLayout(nav)

        self.toc_title = QLabel("暂无目录")
        self.toc_title.setAlignment(Qt.AlignCenter)
        self.toc_title.setStyleSheet("font-size:14px;font-weight:bold;")
        v.addWidget(self.toc_title)
        self.toc_hint = QLabel("请导入文档\n随文章出字自动生成目录")
        self.toc_hint.setAlignment(Qt.AlignCenter)
        self.toc_hint.setObjectName("HintLabel")
        v.addWidget(self.toc_hint)

        ai_btn = QPushButton("AI 识别目录", objectName="FlatBtn")
        ai_btn.clicked.connect(lambda: self.refresh_toc(True))
        v.addWidget(ai_btn, 0, Qt.AlignHCenter)
        self.toc_list = QListWidget()
        self.toc_list.itemClicked.connect(self._toc_clicked)
        v.addWidget(self.toc_list, 1)

        self._nav_body_toc = self.toc_list
        return panel

    def _switch_nav(self, name):
        for n, b in self._nav_tabs.items():
            b.setObjectName("NavTab" + (" Active" if n == name else ""))
            b.style().polish(b)
        # 仅“目录”有实质内容；其余为界面还原
        for w in (self.toc_title, self.toc_hint, self.toc_list):
            w.setVisible(name == "目录")
        if name != "目录":
            self.toc_title.setText(f"{name}（界面还原）")
            self.toc_title.setVisible(True)

    def _build_center(self):
        self.paper = Paper(on_change=self._on_paper_change)
        mm = govstyle.page_margins_mm()
        dpi = 96.0
        self.paper.setViewportMargins(
            int(mm["left"] / 25.4 * dpi), int(mm["top"] / 25.4 * dpi),
            int(mm["right"] / 25.4 * dpi), int(mm["bottom"] / 25.4 * dpi))
        self.paper.document().setDocumentMargin(0)

        self.scroll = QScrollArea(objectName="PageScroll")
        self.scroll.setWidget(self.paper)
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignHCenter)

        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        wrap.addWidget(Ruler())
        wrap.addWidget(self.scroll)
        c = QWidget(); c.setLayout(wrap)
        return c

    def _build_right_panel(self):
        """右侧「样式和格式」任务窗格以静态图片还原（纯视觉）。"""
        panel = QWidget(objectName="RightPanel")
        panel.setFixedWidth(220)
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._sidebar_label = QLabel()
        self._sidebar_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        pm = QPixmap(_asset(f"sidebar_{self.theme}.png"))
        if not pm.isNull():
            self._sidebar_label.setPixmap(pm)
        v.addWidget(self._sidebar_label)
        v.addStretch(1)
        return panel

    # ---------------- 功能 ----------------
    def open_document(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入文档", "", "支持的文档 (*.docx *.txt);;Word 文档 (*.docx);;文本文件 (*.txt)")
        if not path:
            return
        try:
            blocks = docimport.import_file(path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析文档：\n{e}")
            return
        if not blocks:
            QMessageBox.warning(self, "导入失败", "文档内容为空。")
            return
        self.article_path = path
        self.title_doc.setText(os.path.basename(path))
        self.tab_chip_text = os.path.basename(path)
        progress_file = path.rsplit(".", 1)[0] + ".moyu"
        revealed = None
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("blocks") and len(data["blocks"]) == len(blocks):
                    revealed = data["revealed"]
            except (OSError, ValueError):
                pass
        self.paper.load_blocks(blocks, revealed)
        self._update_placeholder()

    def save_progress(self):
        if not self.paper.blocks:
            QMessageBox.information(self, "保存", "还没有导入文档，无进度可保存。")
            return
        default = (self.article_path.rsplit(".", 1)[0] + ".moyu") if self.article_path \
            else os.path.join(os.path.expanduser("~"), "摸鱼进度.moyu")
        path, _ = QFileDialog.getSaveFileName(self, "保存摸鱼进度", default, "摸鱼进度 (*.moyu)")
        if not path:
            return
        self._write_progress(path)
        QMessageBox.information(self, "保存成功", f"摸鱼进度已保存：\n{path}")

    def _write_progress(self, path):
        data = {
            "app": __app_name__, "version": __version__, "build": __build__,
            "article_path": self.article_path,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "blocks": self.paper.blocks,
            "revealed": self.paper.revealed,
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        self._dirty = False

    def restore_last_session(self):
        if not os.path.exists(SESSION_FILE):
            QMessageBox.information(self, "恢复", "没有找到上次会话记录。")
            return
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.article_path = data.get("article_path", "")
            self.title_doc.setText(os.path.basename(self.article_path) or "文字文稿1")
            self.paper.load_blocks(data["blocks"], data["revealed"])
            self._update_placeholder()
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "恢复失败", f"会话记录损坏：{e}")

    def _autosave_tick(self):
        if self.autosave and self._dirty and self.paper.blocks:
            try:
                os.makedirs(SESSION_DIR, exist_ok=True)
                self._write_progress(SESSION_FILE)
            except OSError:
                pass

    def _on_paper_change(self):
        self._dirty = True
        self.refresh_toc()
        total = self.paper.total_chars()
        shown = self.paper.shown_chars()
        pct = (shown * 100 // total) if total else 0
        self.statusBar().showMessage(
            f"摸鱼进度 {shown}/{total} 字（{pct}%）· 撤回 {len(self.paper.undo_stack)} 步 · {__copyright__}")
        if self.paper.blocks and shown >= total:
            self.statusBar().showMessage(f"🎉 全文已摸完！共 {total} 字 · {__copyright__}")

    def refresh_toc(self, from_ai=False):
        self.toc_list.clear()
        seq = []
        for i, b in enumerate(self.paper.blocks):
            if self.paper.revealed[i] > 0 and b["level"] in (1, 2, 3, -1):
                seq.append((i, b))
        if not self.paper.blocks:
            self.toc_title.setText("暂无目录")
            self.toc_hint.setText("请导入文档\n随文章出字自动生成目录")
            return
        if not seq:
            self.toc_title.setText("暂无目录")
            self.toc_hint.setText("目录会随文章出字\n自动逐段生成")
            return
        self.toc_title.setText("目录")
        self.toc_hint.setText(f"已生成 {len(seq)} 条目录")
        for k, (i, b) in enumerate(seq):
            prefix = {1: "  ", 2: "    ", 3: "      ", -1: ""}[b["level"]]
            item = QListWidgetItem(prefix + b["text"][:24])
            item.setData(Qt.UserRole, k)
            self.toc_list.addItem(item)

    def _toc_clicked(self, item):
        self.paper.scroll_to_block(item.data(Qt.UserRole))

    def _jump_to_level(self, level):
        for i, b in enumerate(self.paper.blocks):
            if self.paper.revealed[i] > 0 and b["level"] == level:
                seq = [j for j in range(len(self.paper.blocks)) if self.paper.revealed[j] > 0]
                self.paper.scroll_to_block(seq.index(i))
                return

    def _update_placeholder(self):
        self._on_paper_change()

    # ---------------- 皮肤 ----------------
    def toggle_theme(self):
        self._apply_theme("light" if self.theme == "dark" else "dark")

    def _apply_theme(self, name):
        self.theme = name
        app = QApplication.instance()
        if app:
            app.setStyleSheet(THEMES[name])
        self.skin_btn.setText("☀️ 浅色" if name == "dark" else "🌙 深色")
        # 同步换掉装饰图片（顶部截图 chrome / 右侧样式面板）
        if hasattr(self, "_chrome_label"):
            self._set_chrome_image()
        if hasattr(self, "_sidebar_label"):
            pm = QPixmap(_asset(f"sidebar_{name}.png"))
            if not pm.isNull():
                self._sidebar_label.setPixmap(pm)

    # ---------------- 关于 ----------------
    def show_about(self):
        QMessageBox.about(
            self, f"关于 {__app_name__}",
            f"<b>{__app_name__} {__version__} (Build {__build__})</b><br><br>"
            f"高仿 WPS 摸鱼写作软件：表面在打字办公，实际在逐字“摸”完一整篇文章。<br><br>"
            f"支持拼音/手写等输入法，内置离线结构识别引擎（AI 目录）+ GB/T 9704-2012 公文排版。<br><br>"
            f"{__copyright__}<br>{__license_note__}")

    # ---------------- 关闭 ----------------
    def closeEvent(self, ev):
        if self.paper.blocks and self._dirty:
            try:
                os.makedirs(SESSION_DIR, exist_ok=True)
                self._write_progress(SESSION_FILE)
            except OSError:
                pass
        ev.accept()

    def set_progress_state(self, blocks, revealed, article_path=""):
        self.article_path = article_path
        self.title_doc.setText(os.path.basename(article_path) if article_path else "文字文稿1")
        self.paper.load_blocks(blocks, revealed)
        self._update_placeholder()

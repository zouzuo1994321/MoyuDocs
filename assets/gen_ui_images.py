# -*- coding: utf-8 -*-
"""生成 WPS 风格装饰性界面图片（Ribbon + 样式面板），按深/浅两套主题。
这些图片仅作视觉还原（替代未实现的功能按钮），不绑定任何逻辑。"""

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QBrush
from PySide6.QtCore import Qt, QRect, QSize

THEMES = {
    "light": dict(bg="#f3f3f5", line="#e3e3e6", text="#55595f", weak="#8f9195",
                  rect="#ffffff", rect_line="#dcdce0", accent="#c8452c"),
    "dark": dict(bg="#2b2d31", line="#3a3c40", text="#c2c4c8", weak="#8a8d92",
                 rect="#33353a", rect_line="#44464b", accent="#c8452c"),
}


def _txt(p, x, y, s, font, color, align=Qt.AlignLeft):
    p.setFont(font)
    p.setPen(color)
    p.drawText(x, y, s) if align == Qt.AlignLeft else p.drawText(
        QRect(x, y - 16, 400, 20), align | Qt.AlignVCenter, s)


def make_ribbon(theme):
    t = THEMES[theme]
    W, H = 1360, 92
    pm = QPixmap(W, H)
    pm.fill(QColor(t["bg"]))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # 选项卡行
    tabs = ["开始", "插入", "页面布局", "引用", "审阅", "视图", "工具", "会员专享"]
    x = 12
    ftab = QFont(FONT, 11)
    for i, name in enumerate(tabs):
        w = p.fontMetrics() and 0
        w = 64 if i else 52
        if name == "开始":
            _txt(p, x + 6, 17, name, ftab, QColor(t["accent"]))
            pen = QPen(QColor(t["accent"])); pen.setWidth(2)
            p.setPen(pen)
            p.drawLine(x, 25, x + w, 25)
        else:
            _txt(p, x + 6, 17, name, ftab, QColor(t["weak"]))
        x += w

    # 分组行
    p.setPen(QColor(t["line"]))
    p.drawLine(0, 28, W, 28)

    groups = [
        ("剪贴板", ["粘贴", "剪切", "复制"]),
        ("字体", ["宋体", "三号", "B", "I", "U"]),
        ("段落", ["左", "中", "右", "行距"]),
        ("样式", ["正文", "标题1", "标题2"]),
        ("编辑", ["查找", "替换", "删字"]),
    ]
    gx = 14
    fgroup = QFont(FONT, 10, QFont.Bold)
    fbtn = QFont(FONT, 9)
    for gname, items in groups:
        # 分组竖分隔线
        if gx > 14:
            p.setPen(QColor(t["line"]))
            p.drawLine(gx - 6, 34, gx - 6, H - 6)
        # 组名（底部）
        _txt(p, gx, H - 6, gname, fgroup, QColor(t["weak"]))
        # 按钮
        bx = gx + 2
        for it in items:
            w = 30 if len(it) == 1 else 46
            r = QRect(bx, 36, w, 22)
            p.setBrush(QBrush(QColor(t["rect"])))
            p.setPen(QPen(QColor(t["rect_line"])))
            p.drawRoundedRect(r, 3, 3)
            p.setFont(fbtn)
            p.setPen(QColor(t["text"]))
            p.drawText(r, Qt.AlignCenter, it)
            bx += w + 4
        gx = bx + 16
    p.end()
    return pm


def make_sidebar(theme):
    t = THEMES[theme]
    W, H = 220, 360
    pm = QPixmap(W, H)
    pm.fill(QColor(t["bg"]))
    p = QPainter(pm)
    ftitle = QFont(FONT, 12, QFont.Bold)
    fitem = QFont(FONT, 11)
    _txt(p, 12, 20, "样式和格式", ftitle, QColor(t["text"]))
    fsub = QFont(FONT, 11, QFont.Bold)
    _txt(p, 12, 44, "正文", fsub, QColor(t["text"]))
    _txt(p, 12, 62, "请选择要应用的格式:", fitem, QColor(t["weak"]))
    items = ["标题 1", "标题 2", "标题 3", "标题 4", "默认段落字体", "正文"]
    y = 84
    for i, it in enumerate(items):
        r = QRect(10, y, W - 20, 26)
        if it == "正文":
            p.setBrush(QBrush(QColor(t["rect"])))
            p.setPen(QPen(QColor(t["accent"])))
            p.drawRoundedRect(r, 3, 3)
        else:
            p.setBrush(QBrush(QColor(t["bg"])))
            p.setPen(QColor(t["line"]))
            p.drawRoundedRect(r, 3, 3)
        p.setFont(fitem)
        p.setPen(QColor(t["text"]))
        p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, "   " + it)
        y += 32
    _txt(p, 12, H - 12, "显示: 有效样式", fitem, QColor(t["weak"]))
    p.end()
    return pm


FONT = "Zhuque Fangsong (technical preview)"


def main():
    app = QApplication(sys.argv)
    global FONT
    from PySide6.QtGui import QFontDatabase
    fid = QFontDatabase.addApplicationFont(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts", "ZhuqueFangsong-Regular.ttf"))
    fams = QFontDatabase.applicationFontFamilies(fid)
    if fams:
        FONT = fams[0]
    base = os.path.dirname(os.path.abspath(__file__))
    for theme in ("light", "dark"):
        make_ribbon(theme).save(os.path.join(base, f"ribbon_{theme}.png"))
        make_sidebar(theme).save(os.path.join(base, f"sidebar_{theme}.png"))
    print("UI 图片已生成：ribbon_light/dark.png, sidebar_light/dark.png")


if __name__ == "__main__":
    main()

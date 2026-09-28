# -*- coding: utf-8 -*-
"""GB/T 9704-2012 党政机关公文格式排版。

页面：A4，上边距 37mm、下 35mm、左 28mm、右 26mm（版心 156×225mm）。
字体：
  公文标题（文件大标题）：二号 方正小标宋（回退宋体加粗）
  一级标题：三号 黑体
  二级标题：三号 楷体
  三级标题：三号 仿宋 加粗
  正文：三号 仿宋
  行距：固定值 28 磅（国标推荐 28~30 磅范围取下限）
  首行缩进：2 字符（三号字 ≈ 32 磅）
缺字体时自动加载打包字体（fonts/ 目录下的开源仿宋/黑体/楷体回退字体）。
"""

import os
import sys
import glob

from PySide6.QtGui import QFont, QFontDatabase, QTextBlockFormat, QTextCharFormat, QColor
from PySide6.QtCore import Qt

# 字号（磅）：二号=22，三号=16，小四=12
SIZE_TITLE = 22
SIZE_BODY = 16
LINE_HEIGHT_PT = 28
FIRST_LINE_INDENT_PT = 32  # 2 字符 × 三号 16pt

# 字体族候选链：真实公文用字 → Windows 系统字体 → 打包开源回退字体
FAMILY_XBS = ["方正小标宋简体", "方正小标宋_GBK", "方正小标宋简体_GBK", "宋体", "SimSun"]
FAMILY_HEI = ["黑体", "SimHei"]
FAMILY_KAI = ["楷体", "KaiTi", "楷体_GB2312"]
FAMILY_FANG = ["仿宋", "FangSong", "仿宋_GB2312", "FangSong_GB2312"]

_registered_fonts = []


def app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fonts_dir() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller onefile：字体解包到 _MEIPASS/fonts
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isdir(os.path.join(meipass, "fonts")):
            return os.path.join(meipass, "fonts")
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "fonts")
    return os.path.join(app_base_dir(), "fonts")


def register_bundled_fonts():
    """加载打包字体，返回成功注册的字体族名列表。"""
    families = set(QFontDatabase.families())
    loaded = []
    for path in glob.glob(os.path.join(fonts_dir(), "*.tt[fc]")) + \
                glob.glob(os.path.join(fonts_dir(), "*.otf")):
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            continue
        for fam in QFontDatabase.applicationFontFamilies(fid):
            if fam not in families:
                loaded.append(fam)
                families.add(fam)
    _registered_fonts.extend(loaded)
    return loaded


def _pick_family(candidates):
    fams = set(QFontDatabase.families())
    for c in candidates:
        if c in fams:
            return c
    # 打包回退字体：朱雀仿宋（仿宋）、霞鹜文楷（楷体）、思源黑体
    for fam in QFontDatabase.families():
        if any(k in fam for k in ("朱雀", "Zhuque")) and candidates is FAMILY_FANG:
            return fam
        if any(k in fam for k in ("霞鹜", "LXGW", "LXGW WenKai")) and candidates is FAMILY_KAI:
            return fam
        if any(k in fam for k in ("思源黑体", "Source Han Sans", "Noto Sans CJK", "Noto Sans SC")) and candidates is FAMILY_HEI:
            return fam
    # 兜底
    for fam in QFontDatabase.families():
        if any(k in fam for k in ("宋", "Song", "明朝", " serif", "Serif")):
            return fam
    return "SimSun"


def font_families():
    return {
        "xbs": _pick_family(FAMILY_XBS),
        "hei": _pick_family(FAMILY_HEI),
        "kai": _pick_family(FAMILY_KAI),
        "fang": _pick_family(FAMILY_FANG),
    }


def block_format_for_level(level: int) -> QTextBlockFormat:
    """按国标返回段格式：对齐、行距 28 磅、首行缩进。"""
    fmt = QTextBlockFormat()
    fmt.setLineHeight(LINE_HEIGHT_PT, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
    if level == -1:
        fmt.setAlignment(Qt.AlignCenter)
        fmt.setTopMargin(16)
        fmt.setBottomMargin(16)
    elif level == 0:
        fmt.setAlignment(Qt.AlignJustify)
        fmt.setTextIndent(FIRST_LINE_INDENT_PT)
    else:
        fmt.setAlignment(Qt.AlignJustify)
        fmt.setTextIndent(FIRST_LINE_INDENT_PT)  # 公文标题也首行缩进两字符
    fmt.setTopMargin(0)
    fmt.setBottomMargin(0)
    return fmt


def char_format_for_level(level: int) -> QTextCharFormat:
    """按国标返回字符格式：字体族 + 字号 + 加粗。"""
    fams = font_families()
    cf = QTextCharFormat()
    if level == -1:
        f = QFont(fams["xbs"], SIZE_TITLE)
        f.setBold("宋" in fams["xbs"] or "Song" in fams["xbs"])  # 无小标宋时用宋体加粗模拟
        cf.setFont(f)
    elif level == 1:
        cf.setFont(QFont(fams["hei"], SIZE_BODY))
    elif level == 2:
        cf.setFont(QFont(fams["kai"], SIZE_BODY))
    elif level == 3:
        f = QFont(fams["fang"], SIZE_BODY)
        f.setBold(True)
        cf.setFont(f)
    else:
        cf.setFont(QFont(fams["fang"], SIZE_BODY))
    cf.setForeground(QColor("#1a1a1a"))
    return cf


def page_margins_mm():
    """国标页边距（毫米）：上37 下35 左28 右26。"""
    return {"top": 37.0, "bottom": 35.0, "left": 28.0, "right": 26.0}

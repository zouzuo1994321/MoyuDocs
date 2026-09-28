# -*- coding: utf-8 -*-
"""用 截图/ 里的真实 WPS 截图生成装饰图片：
   - 顶栏+功能区（ribbon_<theme>.png）：裁截图顶部条带
   - 右侧任务窗格（sidebar_<theme>.png）：裁截图右侧条带
裁切比例写在常量里，若效果不理想可直接改这里重跑。"""

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

# 裁切比例（相对原图）。如不满意自行微调。
RIBBON_TOP_FRAC = 0.00      # 从顶部开始（含标题栏）
RIBBON_HEIGHT_FRAC = 0.135  # 取到功能区底部
SIDE_X_FRAC = 0.80          # 右侧栏起始 X
RIBBON_OUT = (1360, 96)     # 输出尺寸（宽度, 高度）
SIDE_OUT = (220, 380)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(PROJECT, "截图")
OUT_DIR = os.path.join(PROJECT, "assets")

MAP = {
    "light": "亮版-1.png",
    "dark": "暗版-1.png",
}


def make():
    app = QApplication(sys.argv)
    os.makedirs(OUT_DIR, exist_ok=True)
    for theme, fname in MAP.items():
        src = os.path.join(SHOT_DIR, fname)
        if not os.path.exists(src):
            print("跳过（无截图）:", src)
            continue
        img = QImage(src)
        if img.isNull():
            print("无法读取:", src)
            continue
        w, h = img.width(), img.height()

        # 顶栏 + 功能区
        ry = int(h * RIBBON_TOP_FRAC)
        rh = int(h * RIBBON_HEIGHT_FRAC)
        band = img.copy(0, ry, w, rh)
        QPixmap.fromImage(band).scaled(
            RIBBON_OUT[0], RIBBON_OUT[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        ).save(os.path.join(OUT_DIR, f"ribbon_{theme}.png"))

        # 右侧任务窗格
        sx = int(w * SIDE_X_FRAC)
        side = img.copy(sx, 0, w - sx, h)
        QPixmap.fromImage(side).scaled(
            SIDE_OUT[0], SIDE_OUT[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        ).save(os.path.join(OUT_DIR, f"sidebar_{theme}.png"))
        print(f"生成 {theme}: {fname} -> ribbon_{theme}.png / sidebar_{theme}.png")

    # 同时把原截图一并打包进 assets/screenshots，便于随时替换
    shot_out = os.path.join(OUT_DIR, "screenshots")
    os.makedirs(shot_out, exist_ok=True)
    for f in os.listdir(SHOT_DIR):
        if f.lower().endswith((".png", ".jpg", ".jpeg")):
            QImage(os.path.join(SHOT_DIR, f)).save(os.path.join(shot_out, f))
    print("原截图已复制到 assets/screenshots/")


if __name__ == "__main__":
    make()

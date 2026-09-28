# -*- coding: utf-8 -*-
"""黑 / 白两套皮肤（仿 WPS Office 配色）。"""

DARK_QSS = """
* { font-family: "Microsoft YaHei UI", "微软雅黑", sans-serif; font-size: 12px; }
QMainWindow, #RootCentral { background: #232428; }
#QuickAccess { background: #232428; border-bottom: 1px solid #2f3033; }
#RibbonTabs { background: #232428; border-bottom: 1px solid #2f3033; }
#FunctionalArea { background: #232428; border-bottom: 1px solid #2f3033; }
.RibbonTab { background: transparent; color: #cfd0d3; border: none; padding: 5px 16px; }
.RibbonTab:hover { background: #33353a; }
.RibbonTab#Active { color: #ffffff; background: #2b2d31; border-bottom: 2px solid #c8452c; }
.NavTab { background: transparent; color: #9a9ca1; border: none; padding: 4px 10px; }
.NavTab:hover { color: #d0d1d4; }
.NavTab#Active { color: #ffffff; border-bottom: 2px solid #c8452c; }
#Ruler { background: #2b2d31; border: none; }
#RibbonTab#Active, .NavTab#Active { font-weight: bold; }
#TitleBar { background: #1b1c1f; border-bottom: 1px solid #2f3033; }
#TitleBar QLabel { color: #d8d9db; }
#TabStrip { background: #1b1c1f; }
#TabChip { background: #2b2d31; border: 1px solid #3a3c40; border-radius: 4px; padding: 3px 10px; color: #d8d9db; }
#TabChip#ActiveTab { background: #232428; border-bottom: 2px solid #c8452c; }
#MenuBar { background: #232428; border-bottom: 1px solid #2f3033; }
#MenuBar QPushButton { color: #cfd0d3; background: transparent; border: none; padding: 5px 12px; border-radius: 4px; }
#MenuBar QPushButton:hover { background: #33353a; }
#MenuBar QPushButton#CheckedTab { color: #e8e9eb; background: #2b2d31; }
#ToolBar { background: #232428; border-bottom: 1px solid #2f3033; }
#ToolBar QToolButton { color: #cfd0d3; background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px 8px; }
#ToolBar QToolButton:hover { background: #33353a; border-color: #44464b; }
#ToolBar QComboBox { background: #2b2d31; color: #d8d9db; border: 1px solid #3a3c40; border-radius: 4px; padding: 2px 8px; }
#LeftPanel, #RightPanel { background: #232428; border-left: 1px solid #2f3033; }
#LeftPanel QLabel, #RightPanel QLabel { color: #a9abaf; }
#LeftPanel QListWidget { background: #26272b; color: #d0d1d4; border: 1px solid #33353a; border-radius: 4px; }
#LeftPanel QListWidget::item { padding: 4px 6px; }
#LeftPanel QListWidget::item:selected { background: #3a4a6b; color: #ffffff; }
#RightPanel QListWidget { background: #26272b; color: #d0d1d4; border: 1px solid #33353a; border-radius: 4px; }
#PageScroll { background: #1b1c1f; border: none; }
#Paper { background: #f7f6f2; border: 1px solid #3a3c40; }
QTextEdit#Paper { color: #1a1a1a; font-family: "仿宋", "FangSong"; font-size: 16px; border: 1px solid #3a3c40; }
#StatusBar { background: #1b1c1f; color: #8f9195; border-top: 1px solid #2f3033; }
QPushButton#PrimaryBtn { background: #c8452c; color: white; border: none; border-radius: 4px; padding: 5px 14px; }
QPushButton#PrimaryBtn:hover { background: #d9553a; }
QPushButton#FlatBtn { background: #2b2d31; color: #cfd0d3; border: 1px solid #3a3c40; border-radius: 4px; padding: 4px 12px; }
QPushButton#FlatBtn:hover { background: #33353a; }
#HintLabel { color: #6f7175; }
QMenu { background: #2b2d31; color: #d8d9db; border: 1px solid #3a3c40; }
QMenu::item:selected { background: #3a4a6b; }
QMessageBox { background: #26272b; color: #d8d9db; }
QMessageBox QLabel { color: #d8d9db; }
QScrollBar:vertical { background: #232428; width: 10px; }
QScrollBar::handle:vertical { background: #45474c; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: #232428; height: 10px; }
QScrollBar::handle:horizontal { background: #45474c; border-radius: 5px; }
"""

LIGHT_QSS = """
* { font-family: "Microsoft YaHei UI", "微软雅黑", sans-serif; font-size: 12px; }
QMainWindow, #RootCentral { background: #f3f3f5; }
#QuickAccess { background: #ffffff; border-bottom: 1px solid #e3e3e6; }
#RibbonTabs { background: #ffffff; border-bottom: 1px solid #e3e3e6; }
#FunctionalArea { background: #ffffff; border-bottom: 1px solid #e3e3e6; }
.RibbonTab { background: transparent; color: #4a4b4f; border: none; padding: 5px 16px; }
.RibbonTab:hover { background: #ececf0; }
.RibbonTab#Active { color: #c8452c; background: #f6ede9; border-bottom: 2px solid #c8452c; }
.NavTab { background: transparent; color: #8f9195; border: none; padding: 4px 10px; }
.NavTab:hover { color: #3a3b3e; }
.NavTab#Active { color: #c8452c; border-bottom: 2px solid #c8452c; }
#Ruler { background: #f3f3f5; border: none; border-bottom: 1px solid #e3e3e6; }
#RibbonTab#Active, .NavTab#Active { font-weight: bold; }
#TitleBar { background: #ffffff; border-bottom: 1px solid #e3e3e6; }
#TitleBar QLabel { color: #3a3b3e; }
#TabStrip { background: #ffffff; }
#TabChip { background: #f3f3f5; border: 1px solid #e3e3e6; border-radius: 4px; padding: 3px 10px; color: #3a3b3e; }
#TabChip#ActiveTab { background: #ffffff; border-bottom: 2px solid #c8452c; }
#MenuBar { background: #ffffff; border-bottom: 1px solid #e3e3e6; }
#MenuBar QPushButton { color: #4a4b4f; background: transparent; border: none; padding: 5px 12px; border-radius: 4px; }
#MenuBar QPushButton:hover { background: #ececf0; }
#MenuBar QPushButton#CheckedTab { color: #c8452c; background: #f6ede9; }
#ToolBar { background: #ffffff; border-bottom: 1px solid #e3e3e6; }
#ToolBar QToolButton { color: #4a4b4f; background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px 8px; }
#ToolBar QToolButton:hover { background: #ececf0; border-color: #d8d8dc; }
#ToolBar QComboBox { background: #f3f3f5; color: #3a3b3e; border: 1px solid #dcdce0; border-radius: 4px; padding: 2px 8px; }
#LeftPanel, #RightPanel { background: #f3f3f5; border-left: 1px solid #e3e3e6; }
#LeftPanel QLabel, #RightPanel QLabel { color: #6f7075; }
#LeftPanel QListWidget { background: #ffffff; color: #3a3b3e; border: 1px solid #e3e3e6; border-radius: 4px; }
#LeftPanel QListWidget::item { padding: 4px 6px; }
#LeftPanel QListWidget::item:selected { background: #e8eefc; color: #2b4a8a; }
#RightPanel QListWidget { background: #ffffff; color: #3a3b3e; border: 1px solid #e3e3e6; border-radius: 4px; }
#PageScroll { background: #e8e8ec; border: none; }
QTextEdit#Paper { background: #ffffff; color: #1a1a1a; font-family: "仿宋", "FangSong"; font-size: 16px; border: 1px solid #d8d8dc; }
#StatusBar { background: #ffffff; color: #8f9195; border-top: 1px solid #e3e3e6; }
QPushButton#PrimaryBtn { background: #c8452c; color: white; border: none; border-radius: 4px; padding: 5px 14px; }
QPushButton#PrimaryBtn:hover { background: #d9553a; }
QPushButton#FlatBtn { background: #ffffff; color: #4a4b4f; border: 1px solid #dcdce0; border-radius: 4px; padding: 4px 12px; }
QPushButton#FlatBtn:hover { background: #ececf0; }
#HintLabel { color: #9a9ba0; }
QMenu { background: #ffffff; color: #3a3b3e; border: 1px solid #e3e3e6; }
QMenu::item:selected { background: #e8eefc; }
QMessageBox { background: #ffffff; color: #3a3b3e; }
QScrollBar:vertical { background: #f3f3f5; width: 10px; }
QScrollBar::handle:vertical { background: #c9c9cf; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: #f3f3f5; height: 10px; }
QScrollBar::handle:horizontal { background: #c9c9cf; border-radius: 5px; }
"""

THEMES = {"dark": DARK_QSS, "light": LIGHT_QSS}

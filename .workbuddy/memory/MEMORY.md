# 摸鱼文书 MoyuDocs — 项目长期记忆

## 产品定位
摸鱼写作软件：拉起**真实 WPS**，把预载文章逐字"打"进真 WPS 窗口（WM_CHAR 直投 _WwG 画布，绕过键盘/IME 链路）。当前 v2.0.9（build 2609280014），PySide6 + PyInstaller 单文件 exe（.spec 驱动，~277MB，含 WebEngine/Multimedia）。README 已按 GitHub 发布规范重写，完整迭代记录在 CHANGELOG.md；用户素材（logo/小说/合同 docx）在 素材/；history/ 只保留最近两版 exe。

## 核心架构
- `moyuapp/wps_driver.py`：WPS 拉起/聚焦/逐字输入。type_char 主路 PostMessageW(WM_CHAR) 直投画布（get_focus_hwnd 用 GetGUIThreadInfo 找 _WwG，缓存 200 字刷新）；\n/\t 走 SendInput；三级兜底 Unicode 注入/剪贴板。send_key/combo/unicode 走 _attach_and_send（AttachThreadInput 防后台"前台锁"丢弃）。ime_open_for_window() 查焦点窗口 IME 开关。
- `moyuapp/keyboard_hook.py`：WH_KEYBOARD_LL。LLKHF_INJECTED=0x10（勿与 EXTENDED=0x01 混淆）。
- `moyuapp/controller.py`：面板+调度。_on_key：注入事件放行→修饰键放行→F9(0x78)→按键模式：编辑键(_EDIT_PASS_VKS)放行、IME 开着放行、否则吞键入队。关于对话框 _on_about=自定义 QDialog（_CONTACTS 四项：GitHub/B站/微博/邮箱）。**closeEvent=关闭即退出（不隐藏托盘）+ _force_kill_later() 1.5s 后 os._exit(0) 兜底**。
- `moyuapp/gongwen.py`：GB/T 9704-2012 公文模板（每块一个空样式段落，纯 zipfile）。
- `moyuapp/ad_popup.py`：假右下角弹窗广告。网页/视频模式 Qt.Window（勿用 Qt.Tool，WebEngine 收不到输入）+ _AdWebPage.createWindow 返回 self 处理 _blank + _make_interactive 置前。**WebEngine 无 H.264/AAC：直链视频(_MEDIA_EXTS)自动转 QMediaPlayer，网页模式有「🌐系统浏览器打开」按钮兜底**。
- 测试：tests/smoke.py 离屏冒烟（QT_QPA_PLATFORM=offscreen），当前 84 项。注意 win.close() 会调度 os._exit(0)，测试须在 1.5s 内收尾。

## 模式语义（用户心智，勿破坏）
- 按键驱动（唯一模式）：**输入法开=手动打字（放行）；输入法关=按键摸鱼（吞键驱动）**；退格/Delete/方向/Home/End/PgUp/PgDn 永远放行（真实删字/导航）。

## 版本节奏（用户惯例）
改完代码 → bump 版本（vX.Y.Z + build YYMMDD####，10位）→ 更新 README + CHANGELOG → 跑离屏冒烟 → PyInstaller .spec 构建（勿传 --onefile/--noconsole/--icon；distpath/workpath 用全新目录）→ 部署根目录 摸鱼文书.exe → 旧版归档 history/ → 追加 .workbuddy/memory/YYYY-MM-DD.md。

## 关键坑（血泪）
1. 中文 IME 会吞 KEYEVENTF_UNICODE 注入字符（EA 语系通病）→ 字符必走 WM_CHAR。
2. 64 位 INPUT 结构体必须 40 字节，否则 SendInput 静默失败。
3. _load_config 回填 UI 控件须 blockSignals，否则信号回写覆盖刚读入的配置。
4. WPS 单实例 + wpscloudsvr.exe 常驻：真机验证可能命中用户常开的其它文档（曾污染"公益专家"文档，未保存）；验证脚本先打字后按窗口标题校验。
5. mock SendInput 必须普通函数（_send_input_list 设 argtypes）；tasklist 输出 GBK 需 decode。
6. git-bash 沙箱下中文文件名 cp 首跑可能假报 cannot stat，提权重跑成功；以文件大小/时间戳核实。
7. 根目录有个 Windows 保留名 `nul` 垃圾文件（64B），删不掉，无害。
8. 修"某模式失效"先看用户截图里的勾选状态确认实际模式（v2.0.5 教训）。
9. **PySide6 QtWebEngine 不含 H.264/AAC 专有编解码器（授权限制，应用层无解）**；离屏环境 runJavaScript 不可靠（探测 canPlayType 返回空），WebEngine 行为别指望离屏实测。
10. PySide6 里 QWebEnginePage 在 QtWebEngineCore 模块（不在 QtWebEngineWidgets），import 错位报 ImportError。
11. git-bash 的 /tmp Windows Python 不识别（解析成 C:\tmp），临时脚本/文件一律用绝对 Windows 路径。
12. 旧版 exe 归档只留最近两版（曾积累 2.4G）；删功能要连配置读取一起删干净（v2.0.7 教训）。

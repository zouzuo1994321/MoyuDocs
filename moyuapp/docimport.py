# -*- coding: utf-8 -*-
"""文档导入与结构识别（内置离线规则引擎，自动理解文件架构）。

支持 .docx（纯 zipfile + XML 解析，无第三方依赖）与 .txt。
输出统一为块列表：每个块 = {"text": str, "level": int}
    level: -1 文件大标题（公文标题）
            0 正文
            1 一级标题（黑体）
            2 二级标题（楷体）
            3 三级标题（仿宋加粗）
"""

import re
import zipfile
import xml.etree.ElementTree as ET

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 中文公文编号正则（用于 txt 及无样式 docx 的层级推断）
RE_CHAPTER = re.compile(r"^第\s*[一二三四五六七八九十百千零〇0-9]+\s*[篇章节条]")
RE_CN_DUN = re.compile(r"^[一二三四五六七八九十]+\s*、")
RE_CN_BRACKET = re.compile(r"^[（(][一二三四五六七八九十]+[）)]")
RE_NUM_DOT = re.compile(r"^\d+(\.\d+)+")
RE_NUM_DUN = re.compile(r"^\d+\s*[、.．](?!\d)")


def _is_doc_title(line: str) -> bool:
    """判断是否为文件大标题：短、无结尾标点、非编号开头。"""
    s = line.strip()
    if not s or len(s) > 40:
        return False
    if RE_CHAPTER.match(s) or RE_CN_DUN.match(s) or RE_CN_BRACKET.match(s) or RE_NUM_DOT.match(s):
        return False
    if s.endswith(("。", "，", "；", "、", "：", ",", ";", ".")):
        return False
    return True


def _detect_level(text: str, style_level: int = None) -> int:
    """优先使用 docx 样式层级，否则用公文编号规则推断。"""
    if style_level is not None:
        return style_level
    s = text.strip()
    if RE_CHAPTER.match(s):
        return 1
    if RE_CN_DUN.match(s):
        # 公文中 “一、” 为一级标题（黑体）
        return 1
    if RE_CN_BRACKET.match(s):
        # “（一）” 为二级标题（楷体）
        return 2
    if RE_NUM_DOT.match(s):
        # 1.1 → 三级（公文常见为三级封顶）
        return 3
    if RE_NUM_DUN.match(s):
        return 3
    return 0


def _style_heading_level(style_id: str, style_name: str):
    """把 docx 段落样式映射为标题层级；非标题返回 None。"""
    for s in (style_id or "", style_name or ""):
        low = s.lower()
        if low in ("title",) or s in ("标题", "文档标题"):
            return -1
        if "heading" in low or "标题" in s:
            m = re.search(r"(\d+)", s)
            if m:
                n = int(m.group(1))
                return max(1, min(3, n))
    return None


def import_docx(path: str):
    """解析 docx：返回块列表。纯标准库实现。"""
    blocks = []
    with zipfile.ZipFile(path) as z:
        xml_data = z.read("word/document.xml")
        # styles.xml 提供样式名映射
        style_names = {}
        try:
            sroot = ET.fromstring(z.read("word/styles.xml"))
            for st in sroot.iter(WORD_NS + "style"):
                sid = st.get(WORD_NS + "styleId", "")
                nm = st.find(WORD_NS + "name")
                sname = nm.get(WORD_NS + "val", "") if nm is not None else ""
                style_names[sid] = sname
        except (KeyError, ET.ParseError):
            pass
    root = ET.fromstring(xml_data)
    body = root.find(WORD_NS + "body")
    if body is None:
        return blocks
    first_nonempty_seen = False
    for p in body.iter(WORD_NS + "p"):
        texts = []
        for t in p.iter(WORD_NS + "t"):
            texts.append(t.text or "")
        text = "".join(texts).strip()
        ppr = p.find(WORD_NS + "pPr")
        style_id = ""
        if ppr is not None:
            ps = ppr.find(WORD_NS + "pStyle")
            if ps is not None:
                style_id = ps.get(WORD_NS + "val", "")
        level = _style_heading_level(style_id, style_names.get(style_id, ""))
        if not text:
            continue  # 公文排版以缩进分段，忽略空行
        if level is None:
            if not first_nonempty_seen and _is_doc_title(text):
                level = -1
            else:
                level = _detect_level(text)
        first_nonempty_seen = True
        blocks.append({"text": text, "level": int(level)})
    return blocks


def import_txt(path: str):
    """解析 txt：自动尝试多种编码。"""
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]  # 去掉空行（公文以缩进分段）
    blocks = []
    for i, line in enumerate(lines):
        if i == 0 and _is_doc_title(line):
            blocks.append({"text": line, "level": -1})
        else:
            blocks.append({"text": line, "level": _detect_level(line)})
    return blocks


def import_pdf(path: str):
    """解析 PDF：用 pypdf 提取文本层，再按行构建块列表。

    扫描件（无文本层）会抛出 ValueError，提示用户先转 docx/txt。
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("缺少 pypdf 组件，无法解析 PDF。")
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)
    text = "\n".join(parts)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    blocks = []
    for i, line in enumerate(lines):
        if i == 0 and _is_doc_title(line):
            blocks.append({"text": line, "level": -1})
        else:
            blocks.append({"text": line, "level": _detect_level(line)})
    if not blocks:
        raise ValueError("该 PDF 没有可提取的文本（可能是扫描件/图片型 PDF），请先转换为 docx 或 txt。")
    return blocks


def import_file(path: str):
    """按扩展名导入，返回块列表。支持 .docx / .txt / .pdf。"""
    low = path.lower()
    if low.endswith(".docx"):
        return import_docx(path)
    if low.endswith(".pdf"):
        return import_pdf(path)
    return import_txt(path)

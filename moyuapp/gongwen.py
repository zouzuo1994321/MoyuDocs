# -*- coding: utf-8 -*-
"""GB/T 9704-2012《党政机关公文格式》模板生成器。

思路：把导入文档的每个段落预置成「空段落 + 国标直接格式」，拉起 WPS 打开该
模板后逐字打入文字，输入天然继承段落样式，无需任何 COM / 界面自动化：

  - 页面 A4，页边距 上37mm 下35mm 左28mm 右26mm（版心 156mm×225mm）；
  - 标题：方正小标宋简体 二号（22pt）居中（缺失时回退宋体加粗）；
  - 正文：仿宋_GB2312 三号（16pt），固定行距 28 磅，首行缩进 2 字符，
    两端对齐，数字/西文 Times New Roman；
  - 一级标题（一、）黑体三号；二级标题（（一））楷体三号；
    三级标题（1.）仿宋三号加粗；
  - 页码：宋体四号，一字线「— N —」包裹，单页码居右、双页码居左
    （evenAndOddHeaders 奇偶页页脚）。

只依赖标准库 zipfile，字体选择由调用方传入本机可用字体族列表。
"""

import zipfile

# ---- 页边距（twips，1mm = 1440/25.4 ≈ 56.7）----
_MM = 1440 / 25.4
MARGIN_TOP = str(round(37 * _MM))      # 2098
MARGIN_BOTTOM = str(round(35 * _MM))   # 1984
MARGIN_LEFT = str(round(28 * _MM))     # 1588
MARGIN_RIGHT = str(round(26 * _MM))    # 1474

SZ_TITLE = "44"    # 二号 22pt（半磅单位）
SZ_BODY = "32"     # 三号 16pt
SZ_PAGE = "28"     # 四号 14pt
LINE_28PT = "560"  # 固定行距 28 磅（二十分之一磅单位）
LINE_TITLE = "640" # 标题行距加大到 32 磅，避免二号字被固定行距裁剪

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
R_NS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
FOOTER_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"


def pick_fonts(families=None):
    """按本机已安装字体族选择国标字体，缺失时逐级回退。

    返回 dict：title/hei/kai/fang/song → 字体名；title_bold → 标题是否加粗。
    """
    fam = set(families or [])

    def pick(*cands):
        for c in cands:
            if c in fam:
                return c
        return cands[-1]

    title = pick("方正小标宋简体", "方正小标宋_GBK", "方正小标宋简体")
    has_title_std = ("方正小标宋简体" in fam) or ("方正小标宋_GBK" in fam)
    return {
        "title": title if has_title_std else "宋体",
        "title_bold": not has_title_std,  # 无小标宋时用宋体加粗近似
        "hei": pick("黑体"),
        "kai": pick("楷体_GB2312", "楷体"),
        "fang": pick("仿宋_GB2312", "仿宋"),
        "song": pick("宋体"),
    }


def _rpr(font_ea, sz, bold=False):
    b = "<w:b/>" if bold else ""
    return ('<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"'
            ' w:eastAsia="%s"/>%s<w:sz w:val="%s"/><w:szCs w:val="%s"/></w:rPr>'
            % (font_ea, b, sz, sz))


def _para_rpr(ppr_body, font_ea, sz, bold=False):
    """生成空段落：段落属性内嵌 rPr（段落标记携带格式 → 打字自动继承）。"""
    return "<w:p><w:pPr>%s%s</w:pPr></w:p>" % (ppr_body, _rpr(font_ea, sz, bold))


def _para_for_block(block, fonts):
    """按块层级生成一个空的国标样式段落。"""
    lvl = block.get("level", 0)
    if lvl == -1:
        ppr = '<w:spacing w:line="%s" w:lineRule="exact"/><w:jc w:val="center"/>' % LINE_TITLE
        return _para_rpr(ppr, fonts["title"], SZ_TITLE, fonts["title_bold"])
    ppr = ('<w:spacing w:line="%s" w:lineRule="exact"/>'
           '<w:ind w:firstLineChars="200" w:firstLine="640"/>'
           '<w:jc w:val="both"/>' % LINE_28PT)
    if lvl == 1:
        return _para_rpr(ppr, fonts["hei"], SZ_BODY)
    if lvl == 2:
        return _para_rpr(ppr, fonts["kai"], SZ_BODY)
    if lvl == 3:
        return _para_rpr(ppr, fonts["fang"], SZ_BODY, bold=True)
    return _para_rpr(ppr, fonts["fang"], SZ_BODY)


def _page_number_runs(fonts, align):
    """「— PAGE —」页码段落；align: right（单页）/ left（双页）。"""
    rpr = _rpr(fonts["song"], SZ_PAGE)
    return (
        '<w:ftr %s %s><w:p><w:pPr><w:jc w:val="%s"/>%s</w:pPr>'
        '<w:r>%s<w:t>— </w:t></w:r>'
        '<w:r>%s<w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r>%s<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r>%s<w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r>%s<w:t>1</w:t></w:r>'
        '<w:r>%s<w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r>%s<w:t> —</w:t></w:r>'
        '</w:p></w:ftr>'
    ) % (W_NS, R_NS, align, rpr, rpr, rpr, rpr, rpr, rpr, rpr, rpr)


def build_docx(path, blocks, families=None):
    """按 GB/T 9704-2012 生成公文模板 docx。

    blocks: docimport.import_file 的块列表；每个块对应一个空段落（样式按层级）。
    families: 本机可用字体族列表（QFontDatabase.families()），用于回退选择。
    """
    fonts = pick_fonts(families)
    paras = "".join(_para_for_block(b, fonts) for b in blocks)
    if not paras:
        paras = _para_rpr('<w:jc w:val="both"/>', fonts["fang"], SZ_BODY)

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<w:document %s><w:body>%s'
        '<w:sectPr>'
        '<w:footerReference w:type="default" r:id="rIdF1"/>'
        '<w:footerReference w:type="even" r:id="rIdF2"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="%s" w:right="%s" w:bottom="%s" w:left="%s"'
        ' w:header="851" w:footer="567" w:gutter="0"/>'
        '<w:pgNumType w:fmt="decimal"/>'
        '</w:sectPr>'
        '</w:body></w:document>'
    ) % (W_NS, paras, MARGIN_TOP, MARGIN_RIGHT, MARGIN_BOTTOM, MARGIN_LEFT)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/word/footer2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdF1" Type="%s" Target="footer1.xml"/>'
        '<Relationship Id="rIdF2" Type="%s" Target="footer2.xml"/>'
        '</Relationships>'
    ) % (FOOTER_REL_TYPE, FOOTER_REL_TYPE)
    settings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<w:settings %s><w:evenAndOddHeaders/></w:settings>' % W_NS
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>摸鱼文书·公文（GB/T 9704-2012）</dc:title></cp:coreProperties>'
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        '<Application>摸鱼文书</Application></Properties>'
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/settings.xml", settings)
        z.writestr("word/footer1.xml", _page_number_runs(fonts, "right"))
        z.writestr("word/footer2.xml", _page_number_runs(fonts, "left"))
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
    return fonts

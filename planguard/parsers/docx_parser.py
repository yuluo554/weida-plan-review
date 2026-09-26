# -*- coding: utf-8 -*-
"""docx 方案解析器（M2）。

- python-docx 按 body 顺序遍历段落与表格（保持章节上下文）；
- 章节识别：标题样式优先（Heading/标题 N），序号正则兜底（共用 base.guess_heading_level）；
- 证据定位：章节路径 + 全文字符偏移；docx 无页码概念，page 为 None；
- 本层只忠实还原文本与定位，数值规范化在 extract 层做（plan/03 §2）。

注意：以"一、"/"3.2"开头的正文行会被识别为章节标题（M2 已知限制，M3 收紧）。
"""
from pathlib import Path

from .base import BaseParser, ParseResult, SectionTracker, guess_heading_level

try:
    import docx as _python_docx
    from docx.oxml.ns import qn as _qn
    from docx.table import Table as _Table
    from docx.text.paragraph import Paragraph as _Paragraph

    HAS_DOCX = True
except ImportError:  # 核心链路零依赖（NFR-03）；未安装时给出可读安装提示
    HAS_DOCX = False


def _iter_block_items(document):
    """按文档顺序产出 Paragraph / Table（python-docx 官方配方）。"""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == _qn("w:p"):
            yield _Paragraph(child, document)
        elif child.tag == _qn("w:tbl"):
            yield _Table(child, document)


def _styled_level(paragraph):
    """标题样式层级（Heading 1/标题 1 → 1..n），无样式返回 None。"""
    style = paragraph.style
    name = style.name if style is not None else ""
    import re
    m = re.search(r"(\d+)", name or "")
    if name.startswith(("Heading", "标题")) and m:
        return int(m.group(1))
    return None


class DocxParser(BaseParser):
    suffixes = (".docx",)

    def parse(self, path) -> ParseResult:
        if not HAS_DOCX:
            raise RuntimeError(
                "解析 .docx 需要 python-docx。请先安装依赖：\n"
                "  py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple python-docx\n"
                "或: pip install -e .[parse]"
            )
        path = Path(path)
        document = _python_docx.Document(str(path))
        result = ParseResult(doc_name=path.name)
        tracker = SectionTracker(result)

        for block in _iter_block_items(document):
            if isinstance(block, _Paragraph):
                if not block.text.strip():
                    continue
                level = _styled_level(block)
                if level is None:
                    level = guess_heading_level(block.text.strip())
                if level:
                    tracker.add_heading(block.text.strip(), level)
                else:
                    tracker.add_line(block.text)
            elif isinstance(block, _Table):
                for row in block.rows:
                    for cell in row.cells:
                        tracker.add_line(cell.text)
        return result

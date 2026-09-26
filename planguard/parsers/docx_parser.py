# -*- coding: utf-8 -*-
"""docx 方案解析器（M2 实现）。

- python-docx 按 body 顺序遍历段落与表格（保持章节上下文）；
- 章节识别：标题样式优先（Heading/标题 N），正则兜底（中文序号"一、"、多级数字"3.2"）；
- 证据定位：章节路径 + 全文字符偏移；docx 无页码概念，page 为 None；
- 本层只忠实还原文本与定位，数值规范化在 extract 层做（plan/03 §2）。

注意：以"一、"/"3.2"开头的正文行会被识别为章节标题（M2 已知限制，M3 收紧）。
"""
import re
from pathlib import Path
from typing import Optional, Tuple

from .base import BaseParser, ParseResult, Section, TextLine

try:
    import docx as _python_docx
    from docx.oxml.ns import qn as _qn
    from docx.table import Table as _Table
    from docx.text.paragraph import Paragraph as _Paragraph

    HAS_DOCX = True
except ImportError:  # 核心链路零依赖（NFR-03）；未安装时给出可读安装提示
    HAS_DOCX = False

RE_CN_SECTION = re.compile(r"^([一二三四五六七八九十百]+)\s*、\s*(\S.*)$")
RE_NUM_SECTION = re.compile(r"^(\d+(?:\.\d+)*)(?:[、.）)]\s*|\s+)(\S.*)$")


def _iter_block_items(document):
    """按文档顺序产出 Paragraph / Table（python-docx 官方配方）。"""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == _qn("w:p"):
            yield _Paragraph(child, document)
        elif child.tag == _qn("w:tbl"):
            yield _Table(child, document)


def _heading_level(paragraph) -> Optional[int]:
    """章节层级：样式名（Heading 1/标题 1）优先，中文/数字序号正则兜底。

    标题以《开头的不算章节（排除"1.《规范名》"这类编制依据条目）。
    """
    style = paragraph.style
    name = style.name if style is not None else ""
    m = re.search(r"(\d+)", name or "")
    if name.startswith(("Heading", "标题")) and m:
        return int(m.group(1))
    text = paragraph.text.strip()
    m = RE_CN_SECTION.match(text)
    if m and not m.group(2).startswith("《"):
        return 1
    m = RE_NUM_SECTION.match(text)
    if m and not m.group(2).startswith("《"):
        return m.group(1).count(".") + 1
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
        stack: list = []  # [(level, full_title)]，path = "/".join(titles)
        offset = 0

        def _add_line(raw: str) -> None:
            nonlocal offset
            text = raw.strip()
            if not text:
                return
            result.lines.append(TextLine(
                text=text,
                section_path="/".join(t for _, t in stack),
                char_start=offset,
                char_end=offset + len(text),
            ))
            offset += len(text) + 1

        for block in _iter_block_items(document):
            if isinstance(block, _Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                level = _heading_level(block)
                if level:
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    stack.append((level, text))
                    result.sections.append(Section(
                        title=text, level=level,
                        path="/".join(t for _, t in stack),
                    ))
                _add_line(block.text)
            elif isinstance(block, _Table):
                for row in block.rows:
                    for cell in row.cells:
                        _add_line(cell.text)
        return result

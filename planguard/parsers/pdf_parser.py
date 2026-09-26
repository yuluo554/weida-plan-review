# -*- coding: utf-8 -*-
"""pdf 方案解析器（M2 实现，仅支持文本型 PDF）。

实现要点（plan/03 §2）：
- pdfplumber 逐页 extract_text + extract_words（词坐标）；
- 按 y 坐标聚类成行，支撑证据定位（页码 + 坐标）；
- 扫描件 OCR 不在范围内（NFR/非目标）。
"""
from pathlib import Path

from .base import BaseParser, ParseResult


class PdfParser(BaseParser):
    suffixes = (".pdf",)

    def parse(self, path) -> ParseResult:
        raise NotImplementedError(
            "pdf 解析器在里程碑 M2 实现（plan/05-里程碑.md）；"
            "先安装依赖: pip install -e .[parse]"
        )

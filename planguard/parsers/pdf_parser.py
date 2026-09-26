# -*- coding: utf-8 -*-
"""pdf 方案解析器（M2，仅支持文本型 PDF）。

- pdfplumber 逐页 extract_text_lines（自带按坐标聚类成行），保留页码进证据链；
- 章节识别共用 base.guess_heading_level（pdf 无样式信息，纯序号正则）；
- 扫描件 OCR 不在范围内（plan/01 非目标）。

陷阱对策（plan/03 §2）：伪空格/全角等数值规范化在 extract 层进行，
本层只负责按阅读顺序还原文本与定位。
"""
from pathlib import Path

from .base import BaseParser, ParseResult, SectionTracker, guess_heading_level

try:
    import pdfplumber as _pdfplumber

    HAS_PDF = True
except ImportError:  # 核心链路零依赖（NFR-03）；未安装时给出可读安装提示
    HAS_PDF = False


class PdfParser(BaseParser):
    suffixes = (".pdf",)

    def parse(self, path) -> ParseResult:
        if not HAS_PDF:
            raise RuntimeError(
                "解析 .pdf 需要 pdfplumber。请先安装依赖：\n"
                "  py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pdfplumber\n"
                "或: pip install -e .[parse]"
            )
        path = Path(path)
        result = ParseResult(doc_name=path.name)
        tracker = SectionTracker(result)

        with _pdfplumber.open(str(path)) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                for item in page.extract_text_lines(strip=True, return_chars=False):
                    text = item.get("text", "").strip()
                    if not text:
                        continue
                    level = guess_heading_level(text)
                    if level:
                        tracker.add_heading(text, level, page=page_no)
                    else:
                        tracker.add_line(text, page=page_no)
        return result

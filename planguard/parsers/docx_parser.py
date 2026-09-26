# -*- coding: utf-8 -*-
"""docx 方案解析器（M2 实现）。

实现要点（plan/03 §2）：
- python-docx 遍历 body 段落与表格；
- 章节识别优先用标题样式（Heading 1–3），正则兜底（"^[一二三四五六七八九十]+、"、"^\\d+(\\.\\d+)*\\s"）；
- 表格逐格抽取并记录行列号；
- 回归陷阱：伪空格、多行合并、全半角、超范围丢弃。
"""
from pathlib import Path

from .base import BaseParser, ParseResult


class DocxParser(BaseParser):
    suffixes = (".docx",)

    def parse(self, path) -> ParseResult:
        raise NotImplementedError(
            "docx 解析器在里程碑 M2 实现（plan/05-里程碑.md）；"
            "先安装依赖: pip install -e .[parse]"
        )

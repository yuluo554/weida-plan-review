# -*- coding: utf-8 -*-
"""方案文档解析器（M2 实现）。

接口契约见 plan/03-模块详设.md §2；实现时必须回归工程陷阱清单
（伪空格/多行合并/CRLF/全半角/区间表达/超范围丢弃）。
"""
from .base import BaseParser, ParseResult, Section, TextLine

__all__ = ["BaseParser", "ParseResult", "Section", "TextLine"]

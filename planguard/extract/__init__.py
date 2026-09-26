# -*- coding: utf-8 -*-
"""参数提取层（M2）：解析中间格式 → 参数卡。规则优先，LLM 兜底 M4 接入。"""
from .extractor import extract_cards, load_aliases

__all__ = ["extract_cards", "load_aliases"]

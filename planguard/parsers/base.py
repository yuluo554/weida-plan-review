# -*- coding: utf-8 -*-
"""解析器抽象基类与中间格式定义（契约，M2 实现）。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Section:
    """章节节点。path 为 "一、工程概况/1.1 ..." 形式的层级路径。"""

    title: str
    level: int = 1
    page: Optional[int] = None
    path: str = ""


@dataclass
class TextLine:
    """一行文本及其定位信息。"""

    text: str
    page: Optional[int] = None
    section_path: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None


@dataclass
class ParseResult:
    """解析中间格式：章节树 + 逐行文本（M2 起由具体解析器产出）。"""

    doc_name: str
    sections: List[Section] = field(default_factory=list)
    lines: List[TextLine] = field(default_factory=list)

    def iter_lines(self):
        return iter(self.lines)


class BaseParser(ABC):
    """解析器接口：parse(path) -> ParseResult。"""

    suffixes: tuple = ()

    def matches(self, path) -> bool:
        return Path(path).suffix.lower() in self.suffixes

    @abstractmethod
    def parse(self, path) -> ParseResult:
        raise NotImplementedError

# -*- coding: utf-8 -*-
"""解析器抽象基类与中间格式定义。

docx / pdf 共用：章节序号推断（guess_heading_level）与章节栈（SectionTracker），
保证两类来源产出一致的证据格式（plan/03 §2）。
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

RE_CN_SECTION = re.compile(r"^([一二三四五六七八九十百]+)\s*、\s*(\S.*)$")
RE_NUM_SECTION = re.compile(r"^(\d+(?:\.\d+)*)(?:[、.）)]\s*|\s+)(\S.*)$")


def guess_heading_level(text: str) -> Optional[int]:
    """无样式信息时的章节推断：中文序号（"一、"）→1 级，多级数字（"3.2"）→对应层级。

    以《开头的条目不算章节（排除"1.《规范名》"这类编制依据条目）。
    """
    m = RE_CN_SECTION.match(text)
    if m and not m.group(2).startswith("《"):
        return 1
    m = RE_NUM_SECTION.match(text)
    if m and not m.group(2).startswith("《"):
        return m.group(1).count(".") + 1
    return None


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
    """解析中间格式：章节树 + 逐行文本。"""

    doc_name: str
    sections: List[Section] = field(default_factory=list)
    lines: List[TextLine] = field(default_factory=list)

    def iter_lines(self):
        return iter(self.lines)


class SectionTracker:
    """维护章节栈并产出带 section_path/字符偏移的行（docx/pdf 共用）。"""

    def __init__(self, result: ParseResult):
        self._result = result
        self._stack: List[Tuple[int, str]] = []
        self._offset = 0

    def path(self) -> str:
        return "/".join(t for _, t in self._stack)

    def add_heading(self, text: str, level: int, page: Optional[int] = None) -> None:
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, text))
        self._result.sections.append(Section(
            title=text, level=level, page=page, path=self.path()))
        self.add_line(text, page=page)

    def add_line(self, raw: str, page: Optional[int] = None) -> None:
        text = raw.strip()
        if not text:
            return
        self._result.lines.append(TextLine(
            text=text,
            page=page,
            section_path=self.path(),
            char_start=self._offset,
            char_end=self._offset + len(text),
        ))
        self._offset += len(text) + 1


class BaseParser(ABC):
    """解析器接口：parse(path) -> ParseResult。"""

    suffixes: tuple = ()

    def matches(self, path) -> bool:
        return Path(path).suffix.lower() in self.suffixes

    @abstractmethod
    def parse(self, path) -> ParseResult:
        raise NotImplementedError

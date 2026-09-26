# -*- coding: utf-8 -*-
"""条文知识库存储与检索（M4 实现）。

L2 条文块：{doc, chapter, article_no, text, tags}
检索：jieba 分词 + TF 余弦（数百条文规模，纯 Python，不引 faiss）。
问答路由：L3 阈值表结构化命中 → 直接回答；否则 L2 检索 top-k → LLM 基于逐字摘录生成。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class CodeBlock:
    """一个条文块（检索与引用的基本单位）。"""

    doc: str          # 来源规范名，如 "GB 50497-2019"
    chapter: str = ""
    article_no: str = ""
    text: str = ""
    tags: List[str] = field(default_factory=list)


def load_blocks(blocks_dir) -> List[CodeBlock]:
    raise NotImplementedError("条文块加载在里程碑 M4 实现（plan/05-里程碑.md）。")


def search(blocks: List[CodeBlock], query: str, top_k: int = 5):
    raise NotImplementedError("余弦检索在里程碑 M4 实现（plan/05-里程碑.md）。")

# -*- coding: utf-8 -*-
"""条文知识库存储与检索（M4）。

L2 条文块：{doc, chapter, article_no, text, tags}（data/knowledge/blocks/*.json）
L3 阈值表：{param, op, value, unit, condition, basis, keywords...}（thresholds/*.json）

检索：**字符 bigram TF 余弦**（纯 Python，零第三方依赖）。
与 plan/03 §4 的偏差说明：原设计 jieba 分词；为实现"核心链路零第三方依赖"（NFR-05），
改用中文字符 bigram + ASCII 词元的 TF 余弦。数百条文规模下召回足够、无词典依赖、
对未登录词（参数名/单位）更稳；接口不变，后续可无缝替换 jieba。

问答路由（ask）：L3 阈值表结构化命中（关键词加权得分达阈值）→ 直接回答并挂条款号；
未命中 → L2 条文块检索 top-k 摘录回答。全部答案标注"待核对，以官方现行文本为准"。
"""
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"

DISCLAIMER = "（整理自公开文件，条目状态：待核对——引用前请以官方现行文本为准）"


@dataclass
class CodeBlock:
    """一个条文块（检索与引用的基本单位）。"""

    doc: str          # 来源规范名，如 "GB 50497-2019"
    chapter: str = ""
    article_no: str = ""
    text: str = ""
    tags: List[str] = field(default_factory=list)
    status: str = "待核对"


@dataclass
class Threshold:
    """一条 L3 机器可读阈值（规则库上游）。"""

    id: str = ""
    param: str = ""
    name: str = ""
    op: str = ""
    value: object = None
    unit: str = ""
    condition: str = ""
    basis: str = ""
    doc: str = ""
    article_no: str = ""
    keywords: List[str] = field(default_factory=list)
    status: str = "待核对"


def _fmt_value(t: Threshold) -> str:
    if isinstance(t.value, list):
        return "～".join(str(v) for v in t.value)
    return str(t.value)


def load_blocks(blocks_dir) -> List[CodeBlock]:
    """加载 blocks 目录下全部 *.json（meta.doc 填充 doc，meta.status_default 填充 status）。"""
    blocks: List[CodeBlock] = []
    for fp in sorted(Path(blocks_dir).glob("*.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        for item in data.get("blocks", []):
            blocks.append(CodeBlock(
                doc=item.get("doc") or meta.get("doc", fp.stem),
                chapter=item.get("chapter", ""),
                article_no=item.get("article_no", ""),
                text=item.get("text", ""),
                tags=list(item.get("tags", [])),
                status=item.get("status", meta.get("status_default", "待核对")),
            ))
    return blocks


def load_thresholds(path) -> List[Threshold]:
    """加载阈值表：目录（扫描 *.json）或单个 json 文件。"""
    path = Path(path)
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    thresholds: List[Threshold] = []
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("thresholds", [])
            meta = data.get("meta", {})
        else:
            items, meta = data, {}
        for item in items:
            thresholds.append(Threshold(
                id=item.get("id", ""),
                param=item.get("param", ""),
                name=item.get("name", ""),
                op=item.get("op", ""),
                value=item.get("value"),
                unit=item.get("unit", ""),
                condition=item.get("condition", ""),
                basis=item.get("basis", ""),
                doc=item.get("doc", "") or meta.get("category", ""),
                article_no=item.get("article_no", ""),
                keywords=list(item.get("keywords", [])),
                status=item.get("status", "待核对"),
            ))
    return thresholds


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+(?:\.[0-9]+)?|\d+(?:\.\d+)?")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> Counter:
    """中文按相邻字符 bigram，ASCII 数字/字母按词元；返回词频 Counter。"""
    # 中文只取相邻字符 bigram：单字入袋会让任意中文查询与全部条文产生重叠，
    # "empty" 路由失效且精度下降；短查询无 bigram 时按未命中处理。
    tokens: List[str] = []
    cjk = _CJK_RE.findall(text)
    tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
    tokens.extend(t.group(0).lower() for t in _TOKEN_RE.finditer(text))
    return Counter(tokens)


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def search(blocks: List[CodeBlock], query: str, top_k: int = 5) -> List[Tuple[CodeBlock, float]]:
    """TF 余弦检索，按得分降序返回 (block, score)；得分为 0 的不返回。"""
    q = _tokenize(query)
    scored = []
    for block in blocks:
        s = _cosine(q, _tokenize(block.text + " " + " ".join(block.tags)))
        if s > 0:
            scored.append((block, s))
    scored.sort(key=lambda x: (-x[1], x[0].doc, x[0].article_no))
    return scored[:top_k]


def match_threshold(thresholds: List[Threshold], query: str,
                    min_score: int = 4) -> Tuple[Optional[Threshold], int]:
    """L3 结构化命中：关键词（按词长加权）在问句中出现则计分，返回 (最佳阈值, 得分)。"""
    best: Optional[Threshold] = None
    best_score = 0
    for t in thresholds:
        score = sum(len(kw) for kw in t.keywords if kw and kw in query)
        if score > best_score:
            best, best_score = t, score
    if best_score >= min_score:
        return best, best_score
    return None, best_score


def format_block(block: CodeBlock) -> str:
    a = (block.article_no or "").strip()
    art = ("第%s条" % a) if re.match(r"^\d", a) else a  # "3.1.2" → 第3.1.2条；"第8章/附件1/（待核对）"原样
    status = "" if (block.status and block.status in art) else (
        "（%s）" % block.status if block.status else "")
    return "《%s》%s %s%s：%s" % (block.doc, block.chapter, art, status, block.text)


def ask(query: str, kdir, top_k: int = 3) -> dict:
    """知识库问答：L3 阈值命中直接回答，否则 L2 条文块 top-k 摘录。

    返回 {"route": "threshold"|"blocks"|"empty", "answer": str, "sources": [...]}。
    """
    kdir = Path(kdir)
    thresholds = load_thresholds(kdir / "thresholds") if (kdir / "thresholds").exists() else []
    blocks = load_blocks(kdir / "blocks") if (kdir / "blocks").exists() else []

    hit, _score = match_threshold(thresholds, query)
    if hit is not None:
        op_text = {"info": "要求：", "enum": "允许取值："}.get(hit.op, "")
        val = op_text + _fmt_value(hit)
        answer = (
            "【阈值表命中·%s】%s：%s%s%s。%s\n依据：%s %s\n%s" % (
                hit.status, hit.name,
                ("要求 " if hit.op not in ("info", "enum") and hit.op else ""), val,
                hit.unit, hit.condition, hit.doc, hit.article_no, hit.basis)
        )
        return {"route": "threshold", "answer": answer,
                "sources": [{"doc": hit.doc, "article_no": hit.article_no, "status": hit.status}]}

    results = search(blocks, query, top_k=top_k)
    if not results:
        return {"route": "empty",
                "answer": "知识库未命中相关条文（当前库为深基坑示例子集）。",
                "sources": []}
    lines = ["【条文检索 top-%d】" % len(results)]
    for block, score in results:
        lines.append("- %s（相关度 %.2f）" % (format_block(block), score))
    lines.append(DISCLAIMER)
    return {"route": "blocks", "answer": "\n".join(lines),
            "sources": [{"doc": b.doc, "chapter": b.chapter, "article_no": b.article_no,
                         "status": b.status} for b, _s in results]}

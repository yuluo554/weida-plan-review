# -*- coding: utf-8 -*-
"""基准评测共用工具（M4）。

环境坑对策（plan/HANDOFF-M4.md）：本机 Python 偶发段错误 → 每份文档跑完立即落盘
（JSONL 诊断流），崩溃不丢已完成结果；--resume 跳过已完成的文档续跑。
"""
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_GOLD_DIR = REPO_ROOT / "data" / "gold"
DEFAULT_SAMPLES_DIR = REPO_ROOT / "data" / "samples"


def load_truths(gold_dir=DEFAULT_GOLD_DIR):
    """按文件名排序加载全部 truth.json。"""
    gold_dir = Path(gold_dir)
    truths = []
    for fp in sorted(gold_dir.glob("*.truth.json")):
        truths.append(json.loads(fp.read_text(encoding="utf-8")))
    return truths


def value_match(expected, got) -> bool:
    """数值字段匹配（浮点容差）；文本字段精确相等。"""
    if isinstance(expected, str) or isinstance(got, str):
        return str(expected) == str(got)
    if expected is None or got is None:
        return expected is None and got is None
    return math.isclose(float(expected), float(got), rel_tol=1e-9, abs_tol=1e-9)


class JsonlDiag:
    """逐行 JSONL 诊断流：写一条刷一条，崩溃可续跑（--resume 复用已完成行）。"""

    def __init__(self, path, resume=False):
        self.path = Path(path)
        self.done = {}
        if resume and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 崩溃留下的半行，丢弃
                if isinstance(rec, dict) and rec.get("file"):
                    self.done[rec["file"]] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")

    def has(self, name: str) -> bool:
        return name in self.done

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def prf(tp: int, fp: int, fn: int) -> dict:
    """P/R/F1；分母为 0 时约定该指标为 1.0（无预测且无真值 → 完美）。"""
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": p, "recall": r, "f1": f,
            "tp": tp, "fp": fp, "fn": fn}

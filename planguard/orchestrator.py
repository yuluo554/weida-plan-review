# -*- coding: utf-8 -*-
"""端到端流水线编排（M3 接通）。

轻量状态机：load_doc → parse → extract_cards → load_rules → check → merge_verdicts → report
每节点记录耗时与输入输出计数；CLI check 与 Web 面板共用本编排器。
"""
from dataclasses import dataclass, field
from typing import List

STAGES = ("load_doc", "parse", "extract_cards", "load_rules", "check", "merge_verdicts", "report")


@dataclass
class StageRecord:
    name: str
    status: str = "pending"   # pending / ok / error / skipped
    seconds: float = 0.0
    note: str = ""


@dataclass
class PipelineTrace:
    doc: str = ""
    stages: List[StageRecord] = field(default_factory=list)


def run(doc_path, out_dir) -> PipelineTrace:
    """端到端审查：方案文档进，ReviewResult + 报告出。M3 实现。"""
    raise NotImplementedError(
        "端到端流水线在里程碑 M3 接通（plan/05-里程碑.md）。"
        "当前可运行 `py -m planguard demo` 查看骨架演示。"
    )

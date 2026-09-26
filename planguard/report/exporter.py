# -*- coding: utf-8 -*-
"""报告导出（M3 Markdown / M5 docx）。

报告结构（plan/03 §7）：封面 → 总体结论 → 不合规清单 → 待人工确认 →
通过项 → 参数卡附录 → 签署栏。报告不替代专家论证。
"""
from pathlib import Path


def export_markdown(result, out_path) -> Path:
    raise NotImplementedError("Markdown 报告在里程碑 M3 实现（plan/05-里程碑.md）。")


def export_docx(result, out_path) -> Path:
    raise NotImplementedError(
        "docx 报告在里程碑 M5 实现（plan/05-里程碑.md）；"
        "先安装依赖: pip install -e .[parse]"
    )

# -*- coding: utf-8 -*-
"""配对真值数据生成器（M1–M2 实现，设计见 plan/04-数据计划.md §2）。

用法（实现后）:
    py scripts/make_gold.py --out data/samples --gold data/gold --count 10

生成: samples/gen_XXXX.docx + gold/gen_XXXX.truth.json
（每张参数卡真值 + 注入差异清单：漏章节/超阈值/频率不足/单位错误/多值冲突）
"""
import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="危大方案配对真值数据生成器（骨架占位）")
    parser.add_argument("--out", default="data/samples", help="样例输出目录")
    parser.add_argument("--gold", default="data/gold", help="真值输出目录")
    parser.add_argument("--count", type=int, default=10, help="生成份数")
    parser.add_argument("--category", choices=["deep_pit", "formwork_support"], default="deep_pit")
    args = parser.parse_args(argv)

    print("骨架阶段：生成器尚未实现，设计见 plan/04-数据计划.md §2；计划在里程碑 M2 落地。", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())

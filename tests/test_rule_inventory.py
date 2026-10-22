# -*- coding: utf-8 -*-
"""规则库计数守门（D1：README/CLI 曾把 29 条写成「深基坑 20 + 高支模 10」）。

它守三件事，防止自述数字再次漂移：
1. 规则总数与两类目计数等于实测值（改规则必须同步改这里，是刻意的）；
2. README 特性表里的规则数字与实测一致；
3. CLI ``info`` 的规则库文案由 category 统计生成，不出现硬编码的旧数字。
"""
import re
import unittest
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from planguard import cli
from planguard.rules import load_rules
from planguard.rules.engine import DEFAULT_RULES_DIR

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"

# ★ 实测基线（增删规则时必须同步这两行）
TOTAL = 29
BY_CATEGORY = {"deep_pit": 19, "formwork_support": 10}


class TestRuleInventory(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules(Path(DEFAULT_RULES_DIR))

    def test_total_and_categories(self):
        self.assertEqual(len(self.rules), TOTAL)
        self.assertEqual(dict(Counter(r.category for r in self.rules)), BY_CATEGORY)

    def test_readme_states_same_numbers(self):
        text = README.read_text(encoding="utf-8")
        want = "深基坑 %d + 高支模 %d = %d 条" % (
            BY_CATEGORY["deep_pit"], BY_CATEGORY["formwork_support"], TOTAL)
        self.assertIn(want, text, "README 规则数字与实测不一致（应为 %r）" % want)

    def test_readme_has_no_stale_rule_count(self):
        text = README.read_text(encoding="utf-8")
        # 旧错值：把规则数写成 20
        self.assertNotRegex(text, r"深基坑\s*20\s*\+\s*高支模", "README 仍有「深基坑 20」旧错值")

    def test_cli_info_text_is_derived(self):
        buf = StringIO()
        with redirect_stdout(buf):
            cli.cmd_info(None)
        out = buf.getvalue()
        want = "深基坑 %d + 高支模 %d = %d 条" % (
            BY_CATEGORY["deep_pit"], BY_CATEGORY["formwork_support"], TOTAL)
        self.assertIn(want, out, "CLI info 规则库文案应为 %r" % want)
        self.assertNotRegex(out, r"深基坑\s*20", "CLI info 仍有「深基坑 20」旧错值")
        self.assertIn("[%d 条] rules/data" % TOTAL, out)

    def test_cli_inventory_helper_matches(self):
        self.assertEqual(cli._rules_inventory(self.rules),
                         "深基坑 %d + 高支模 %d = %d 条" % (
                             BY_CATEGORY["deep_pit"], BY_CATEGORY["formwork_support"], TOTAL))


if __name__ == "__main__":
    unittest.main()

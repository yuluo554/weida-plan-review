# -*- coding: utf-8 -*-
"""骨架冒烟测试：CLI、IR 往返、规则加载与引擎裁决。零第三方依赖，`py -m unittest discover` 可跑。"""
import contextlib
import io
import unittest

from planguard import __version__
from planguard.ir.schema import Evidence, ParameterCard, ReviewResult
from planguard.rules.engine import DEFAULT_RULES_DIR, RuleEngine, RuleError, load_rules


def _cards(*pairs):
    """(param_id, value, unit) 快捷构造参数卡。"""
    return [
        ParameterCard(param_id=pid, name=pid, value=v, unit=u,
                      evidence=Evidence(doc="t.docx", line_text="测试行"))
        for pid, v, u in pairs
    ]


class TestCli(unittest.TestCase):
    def test_help_exits_zero(self):
        from planguard.cli import main

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(buf):
                main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("demo", buf.getvalue())

    def test_info_shows_version(self):
        from planguard.cli import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["info"])
        self.assertEqual(rc, 0)
        self.assertIn(__version__, buf.getvalue())

    def test_parse_stub_exit_code_3(self):
        from planguard.cli import main

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = main(["parse", "不存在.docx"])
        self.assertEqual(rc, 3)  # 3 = 功能尚未实现（py -m planguard 时为进程退出码）

    def test_demo_runs(self):
        from planguard.cli import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["demo"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("总体结论", out)
        self.assertIn("R-DP-021", out)


class TestRules(unittest.TestCase):
    def test_sample_rules_load(self):
        rules = load_rules(DEFAULT_RULES_DIR)
        self.assertGreaterEqual(len(rules), 5)
        ids = {r.id for r in rules}
        self.assertIn("R-DP-021", ids)

    def test_invalid_rule_rejected(self):
        import json
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([{"id": "X", "name": "坏规则"}], f, ensure_ascii=False)
        try:
            with self.assertRaises(RuleError):
                load_rules(path)
        finally:
            os.unlink(path)


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(load_rules(DEFAULT_RULES_DIR))

    def test_all_pass(self):
        cards = _cards(
            ("dp.excavation_depth", 5.4, "m"),
            ("dp.retaining.displacement", 25.0, "mm"),
            ("dp.monitoring.frequency", 2.0, "次/d"),
            ("fs.support.height", 6.0, "m"),
        )
        findings, skipped = self.engine.check(cards)
        self.assertEqual(len(skipped), 0)  # enabled 规则全部可分派
        self.assertEqual(len(self.engine.disabled), 1)  # R-DP-101 conditional_program 未启用
        self.assertEqual(len(findings), 4)
        self.assertTrue(all(f.result == "pass" for f in findings))

    def test_threshold_fail(self):
        cards = _cards(
            ("dp.excavation_depth", 5.4, "m"),
            ("dp.retaining.displacement", 35.0, "mm"),
            ("dp.monitoring.frequency", 0.5, "次/d"),
            ("fs.support.height", 6.0, "m"),
        )
        findings, _ = self.engine.check(cards)
        results = {f.rule_id: f.result for f in findings}
        self.assertEqual(results["R-DP-021"], "fail")
        self.assertEqual(results["R-DP-031"], "fail")
        self.assertIn("35", {f.rule_id: f.detail for f in findings}["R-DP-021"])

    def test_multi_value_conflict_goes_manual(self):
        cards = _cards(
            ("dp.excavation_depth", 5.4, "m"),
            ("dp.retaining.displacement", 28.0, "mm"),
            ("dp.retaining.displacement", 40.0, "mm"),
            ("dp.monitoring.frequency", 2.0, "次/d"),
            ("fs.support.height", 6.0, "m"),
        )
        findings, _ = self.engine.check(cards)
        by_id = {f.rule_id: f.result for f in findings}
        self.assertEqual(by_id["R-DP-021"], "manual")

    def test_missing_required_param_fails(self):
        cards = _cards(("dp.excavation_depth", 5.4, "m"))
        findings, _ = self.engine.check(cards)
        by_id = {f.rule_id: f.result for f in findings}
        self.assertEqual(by_id["R-FS-001"], "fail")
        self.assertEqual(by_id["R-DP-001"], "pass")


class TestIR(unittest.TestCase):
    def test_card_json_roundtrip(self):
        card = ParameterCard(
            param_id="dp.excavation_depth", name="基坑开挖深度", value=5.4, unit="m",
            raw_text="5.4m", category="deep_pit",
            evidence=Evidence(doc="a.docx", section="一、工程概况", page=3, line_text="深度5.4m"),
        )
        clone = ParameterCard.from_dict(card.to_dict())
        self.assertEqual(clone.param_id, card.param_id)
        self.assertEqual(clone.value, card.value)
        self.assertEqual(clone.evidence.line_text, "深度5.4m")

    def test_review_result_summary(self):
        from planguard.ir.schema import Finding

        result = ReviewResult(doc="x", findings=[
            Finding("a", "a", result="pass"),
            Finding("b", "b", result="fail"),
            Finding("c", "c", result="manual"),
        ])
        self.assertEqual(result.summary(), {"pass": 1, "fail": 1, "manual": 1})


if __name__ == "__main__":
    unittest.main()

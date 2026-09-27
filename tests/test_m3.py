# -*- coding: utf-8 -*-
"""M3 测试：规则引擎新 check_type、类目门控、编排器端到端、报告导出。"""
import json
import tempfile
import unittest
from pathlib import Path

from planguard.ir.schema import Evidence, ParameterCard, ReviewResult
from planguard.parsers.base import ParseResult, Section, TextLine
from planguard.report.exporter import export_markdown
from planguard.rules.engine import DEFAULT_RULES_DIR, RuleEngine, load_rules

try:
    from planguard.parsers.docx_parser import HAS_DOCX
except ImportError:  # pragma: no cover
    HAS_DOCX = False

REPO = Path(__file__).resolve().parents[1]
SAMPLES = REPO / "data" / "samples"
GOLD = REPO / "data" / "gold"


def _card(pid, value=None, unit="", text_value=None):
    return ParameterCard(param_id=pid, name=pid, value=value, unit=unit,
                         text_value=text_value,
                         evidence=Evidence(doc="t.docx", line_text="测试行"))


def _doc(*lines, sections=()):
    return ParseResult(
        doc_name="t.docx",
        sections=[Section(title=t, level=1, path=t) for t in sections],
        lines=[TextLine(text=t, section_path="") for t in lines],
    )


class EngineCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(load_rules(DEFAULT_RULES_DIR))


class TestWithinRange(EngineCase):
    def _rule(self, rules_dir=DEFAULT_RULES_DIR):
        from planguard.rules.engine import Rule

        return Rule(id="T1", name="区间", check_type="within_range", param="p.x",
                    basis="测试依据", min_value=10, max_value=30)

    def test_pass_and_fail(self):
        engine = RuleEngine([self._rule()])
        ok, _ = engine.check([_card("p.x", 20)])
        bad, _ = engine.check([_card("p.x", 35)])
        self.assertEqual(ok[0].result, "pass")
        self.assertEqual(bad[0].result, "fail")
        self.assertIn("[10, 30]", bad[0].detail)

    def test_boundary_inclusive(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([_card("p.x", 10)])
        self.assertEqual(findings[0].result, "pass")


class TestEnum(EngineCase):
    def _rule(self):
        from planguard.rules.engine import Rule

        return Rule(id="T2", name="枚举", check_type="enum", param="p.kind",
                    basis="测试依据", allowed=["桩锚支护", "放坡"])

    def test_exact_and_contains_match(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([_card("p.kind", text_value="桩锚支护")])
        self.assertEqual(findings[0].result, "pass")
        # 双向包含：短文本"桩锚"被 allowed 中的"桩锚支护"包含
        findings, _ = engine.check([_card("p.kind", text_value="桩锚")])
        self.assertEqual(findings[0].result, "pass")

    def test_fail_on_out_of_set(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([_card("p.kind", text_value=" magic ")])
        self.assertEqual(findings[0].result, "fail")


class TestConditional(EngineCase):
    def _rule(self):
        from planguard.rules.engine import Rule

        return Rule(id="T3", name="条件程序", check_type="conditional_program",
                    param="dp.excavation_depth", basis="测试依据",
                    condition={"min": 5}, require_text="专家论证")

    def test_triggered_missing_text_fails(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([_card("dp.excavation_depth", 5.4)],
                                   doc=_doc("基坑开挖深度为5.4m。"))
        self.assertEqual(findings[0].result, "fail")

    def test_triggered_with_text_passes(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([_card("dp.excavation_depth", 5.4)],
                                   doc=_doc("已组织专家论证。"))
        self.assertEqual(findings[0].result, "pass")

    def test_not_triggered_no_finding(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([_card("dp.excavation_depth", 4.6)],
                                   doc=_doc("深度4.6m，无论证。"))
        self.assertEqual(findings, [])

    def test_needs_doc_goes_skipped(self):
        engine = RuleEngine([self._rule()])
        findings, skipped = engine.check([_card("dp.excavation_depth", 5.4)])
        self.assertEqual(findings, [])
        self.assertEqual([r.id for r in skipped], ["T3"])


class TestChecklist(EngineCase):
    def _rule(self):
        from planguard.rules.engine import Rule

        return Rule(id="T4", name="章节齐套", check_type="checklist_section",
                    param="doc.sections", basis="测试依据",
                    sections=[{"title": "应急处置措施", "keywords": ["应急处置", "应急预案"]},
                              {"title": "验收要求", "keywords": ["验收"]}])

    def test_missing_reported(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([], doc=_doc(sections=["一、工程概况", "二、验收要求"]))
        self.assertEqual(findings[0].result, "fail")
        self.assertIn("应急处置措施", findings[0].detail)

    def test_all_present_passes(self):
        engine = RuleEngine([self._rule()])
        findings, _ = engine.check([], doc=_doc(sections=["应急处置措施", "验收要求"]))
        self.assertEqual(findings[0].result, "pass")


class TestOnlyIfTextGate(EngineCase):
    """类目门控：深基坑方案不查高支模参数（R-FS-001 仅当全文提及模板/高支模时生效）。"""

    def test_gate_off_no_finding(self):
        findings, _ = self.engine.check([], doc=_doc("基坑开挖深度为5.4m，采用放坡+土钉墙支护。"))
        self.assertNotIn("R-FS-001", {f.rule_id for f in findings})

    def test_gate_on_missing_fails(self):
        findings, _ = self.engine.check([], doc=_doc("本工程高支模搭设详见工艺章节。"))
        fs = [f for f in findings if f.rule_id == "R-FS-001"]
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0].result, "fail")


class TestReportAndOrchestrator(unittest.TestCase):
    def test_markdown_export(self):
        from planguard.ir.schema import Finding

        result = ReviewResult(doc="样例.docx", findings=[
            Finding("A-1", "规则A", result="fail", basis="依据X", detail="超限", advice="整改"),
            Finding("B-1", "规则B", result="pass", basis="依据Y", detail="满足"),
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "r.md"
            path = export_markdown(result, out)
            text = path.read_text(encoding="utf-8")
        self.assertIn("# PlanGuard 专项施工方案审查报告", text)
        self.assertIn("**总体结论: 不合规**", text)
        self.assertIn("## 三、待人工确认清单", text)
        self.assertIn("签署栏", text)


@unittest.skipUnless(HAS_DOCX, "python-docx 未安装")
class TestEndToEndInjection(unittest.TestCase):
    """M3 DoD：10 份生成样例的全部注入差异，端到端审查按预期命中。"""

    @classmethod
    def setUpClass(cls):
        from planguard.orchestrator import run

        # staticmethod：实例访问时才不会绑定 self（且命名不能是 run——会覆盖 TestCase.run）
        cls.run_pipeline = staticmethod(run)
        cls.results = {}
        for tf in sorted(GOLD.glob("*.truth.json")):
            truth = json.loads(tf.read_text(encoding="utf-8"))
            result, trace = cls.run_pipeline(SAMPLES / truth["file"])
            cls.results[truth["file"]] = (truth, result, trace)

    def test_all_injections_hit(self):
        for fname, (truth, result, _) in self.results.items():
            got = {(f.rule_id, f.result) for f in result.findings}
            for inj in truth["injected"]:
                expect = inj.get("expect", {})
                if "rule_id" in expect:
                    self.assertIn((expect["rule_id"], expect["result"]), got,
                                  msg="%s 注入差异未命中: %s" % (fname, inj))

    def test_trace_stages_ok(self):
        for fname, (_, _, trace) in self.results.items():
            self.assertTrue(all(s.status == "ok" for s in trace.stages), msg=fname)
            self.assertEqual(trace.stages[-1].name, "check")  # 未导出报告时最后为 check

    def test_pipeline_with_report(self):
        with tempfile.TemporaryDirectory() as td:
            result, trace = self.run_pipeline(SAMPLES / "gen_0001.docx", out_dir=Path(td))
            report = Path(result.meta["report"])
            self.assertTrue(report.exists())
            text = report.read_text(encoding="utf-8")
            self.assertIn("总体结论", text)
            self.assertEqual(trace.stages[-1].name, "report_docx")  # M5：末尾追加 docx 报告阶段
            self.assertIn("report", [st.name for st in trace.stages])


if __name__ == "__main__":
    unittest.main()

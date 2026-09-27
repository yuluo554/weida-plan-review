# -*- coding: utf-8 -*-
"""M5 测试：高支模类目（生成/提取/规则门控）、docx 审查报告、Web 面板、知识库扩量。

全部离线：Web 用 FastAPI TestClient（内存请求）；LLM 不参与本里程碑新增逻辑。
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from planguard.ir.schema import ParameterCard
from planguard.rules.engine import RuleEngine, load_rules

REPO = Path(__file__).resolve().parents[1]


def has_docx():
    try:
        import docx  # noqa: F401
        return True
    except ImportError:
        return False


class TestGoldgenFS(unittest.TestCase):
    """高支模生成器：自然参数不触发非 pass 结论的口径对深基坑同样成立。"""

    @classmethod
    def setUpClass(cls):
        if not has_docx():
            raise unittest.SkipTest("python-docx 未安装")
        import tempfile as _tf
        cls.tmp = _tf.TemporaryDirectory()
        from planguard.goldgen import generate
        cls.tmp_path = Path(cls.tmp.name)
        cls.truths = generate(cls.tmp_path / "s", cls.tmp_path / "g",
                              count=5, seed=99, category="formwork_support")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_truth_shape(self):
        for t in self.truths:
            self.assertEqual(t["category"], "formwork_support")
            self.assertTrue(t["file"].startswith("fs_"))
            for inj in t["injected"]:
                self.assertIn(inj["expect"]["result"], ("fail", "manual"))
        types = {i["type"] for t in self.truths for i in t["injected"]}
        self.assertEqual(types, {"over_height", "low_spacing", "multi_height",
                                 "unit_error", "missing_section"})

    def test_extract_matches_truth(self):
        sys.path.insert(0, str(REPO / "benchmarks"))
        from benchmarks.eval_parse import match_param  # 复用同一匹配口径
        from planguard.extract import extract_cards
        from planguard.parsers.docx_parser import DocxParser

        for truth in self.truths:
            parsed = DocxParser().parse(self.tmp_path / "s" / truth["file"])
            cards, _meta = extract_cards(parsed)
            grouped = {}
            for c in cards:
                bucket = grouped.setdefault(c.param_id, {"values": [], "texts": []})
                (bucket["texts"] if c.text_value is not None else bucket["values"]).append(
                    c.text_value if c.text_value is not None else c.value)
            for param_id, expected in truth["expected_cards"].items():
                m = match_param(expected, grouped.get(param_id, {"values": [], "texts": []}))
                self.assertEqual((m["fp"], m["fn"]), (0, 0),
                                 "%s %s: %s" % (truth["file"], param_id, m))

    def test_fs_rules_gate_on_deep_pit_and_vice_versa(self):
        """类目互斥：深基坑规则不吃高支模文档，反之亦然（M5 门控修复）。"""
        from planguard.orchestrator import run

        fs_doc = self.tmp_path / "s" / self.truths[0]["file"]
        result_fs, _ = run(fs_doc)
        self.assertFalse([f for f in result_fs.findings if f.rule_id.startswith("R-DP-")
                          and f.result in ("fail", "manual")])

        dp_doc = REPO / "data" / "samples" / "gen_0001.docx"
        result_dp, _ = run(dp_doc)
        self.assertFalse([f for f in result_dp.findings if f.rule_id.startswith("R-FS-")
                          and f.result in ("fail", "manual")])


class TestFSRules(unittest.TestCase):
    def test_rule_library_loads(self):
        rules = load_rules(REPO / "planguard" / "rules" / "data")
        ids = {r.id for r in rules}
        self.assertIn("R-FS-001", ids)
        for rid in ("R-FS-002", "R-FS-003", "R-FS-004", "R-FS-012",
                    "R-FS-031", "R-FS-041", "R-FS-051", "R-FS-101", "R-FS-102"):
            self.assertIn(rid, ids)
        self.assertEqual(len(ids), len(rules), "规则 id 不得重复")
        for r in rules:
            if r.category == "formwork_support" and r.check_type in (
                    "required", "threshold_max", "within_range", "enum",
                    "conditional_program", "checklist_section"):
                self.assertTrue(r.only_if_text, "%s 缺少 only_if_text 类目门控" % r.id)

    def test_threshold_engine_paths(self):
        """R-FS-031/012/101 的正反例（多值 manual / 缺参跳过）。"""
        rules = {r.id: r for r in load_rules(REPO / "planguard" / "rules" / "data"
                                             / "formwork_support.json")}
        ev = {"doc": "t.docx", "section": "", "line_text": ""}
        card = lambda v, pid="fs.pole.spacing": ParameterCard(  # noqa: E731
            param_id=pid, name="x", value=v, unit="m", category="formwork_support",
            evidence=None)
        engine = RuleEngine(list(rules.values()))

        findings, _ = engine.check([card(1.5)])
        by = {f.rule_id: f.result for f in findings}
        self.assertEqual(by.get("R-FS-031"), "fail")

        findings, _ = engine.check([card(0.5), card(0.9)])
        self.assertIn("manual", [f.result for f in findings if f.rule_id == "R-FS-031"])


class TestDocxReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not has_docx():
            raise unittest.SkipTest("python-docx 未安装")
        from planguard.orchestrator import run
        cls.result, _trace = run(REPO / "data" / "samples" / "gen_0001.docx")

    def test_export_docx_structure(self):
        import docx as docxlib
        from planguard.report.exporter import export_docx

        with tempfile.TemporaryDirectory() as tmp:
            out = export_docx(self.result, Path(tmp) / "r.docx")
            document = docxlib.Document(str(out))
        heads = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
        self.assertIn("一、总体结论", heads)
        self.assertIn("二、不合规清单", heads)
        self.assertIn("六、签署栏", heads)
        self.assertGreaterEqual(len(document.tables), 4)  # 结论/不合规/参数卡/签署栏

    def test_orchestrator_exports_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            from planguard.orchestrator import run
            result, _ = run(REPO / "data" / "samples" / "fs_0001.docx", out_dir=tmp)
            self.assertTrue(Path(result.meta["report"]).exists())
            self.assertTrue(Path(result.meta["report_docx"]).exists())


class TestWebPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            raise unittest.SkipTest("fastapi/httpx 未安装（pip install -e .[web]）")
        from planguard.web.app import create_app
        cls.client = TestClient(create_app())

    def test_health_and_index(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertIn("version", r.json())
        r2 = self.client.get("/")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("PlanGuard", r2.text)

    def test_vendor_is_local_only(self):
        """断网口径：页面唯一脚本是本地 vendor，全文无外链。"""
        html = self.client.get("/").text
        self.assertIn("/vendor/vue.global.prod.js", html)
        self.assertNotIn("http://", html.replace('xmlns', ''))  # 无 CDN 外链
        self.assertNotIn("https://", html)
        r = self.client.get("/vendor/vue.global.prod.js")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 100000)

    def test_review_endpoint(self):
        doc = REPO / "data" / "samples" / "gen_0001.docx"
        with doc.open("rb") as fh:
            r = self.client.post("/api/review",
                                 files={"file": (doc.name, fh, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["doc"], "gen_0001.docx")
        self.assertEqual(set(data["summary"]), {"pass", "fail", "manual"})
        self.assertTrue(data["stages"])
        self.assertTrue(data["findings"])

    def test_review_rejects_bad_suffix(self):
        r = self.client.post("/api/review",
                             files={"file": ("x.exe", b"123", "application/x-msdownload")})
        self.assertEqual(r.status_code, 400)

    def test_ask_endpoint(self):
        r = self.client.post("/api/ask", json={"query": "基坑开挖深度超过多少需要专家论证"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["route"], "threshold")
        r2 = self.client.post("/api/ask", json={"query": ""})
        self.assertEqual(r2.status_code, 400)


class TestKnowledgeFS(unittest.TestCase):
    """知识库扩量：高支模阈值表 ≥15 条、JGJ 162 条文块入库，全部待核对。"""

    @classmethod
    def setUpClass(cls):
        from planguard.knowledge.store import load_blocks, load_thresholds
        cls.thresholds = load_thresholds(REPO / "data" / "knowledge" / "thresholds")
        cls.blocks = load_blocks(REPO / "data" / "knowledge" / "blocks")

    def test_scale_and_status(self):
        fs = [t for t in self.thresholds if t.param.startswith("fs.")]
        self.assertGreaterEqual(len(fs), 15)
        docs = {b.doc for b in self.blocks}
        self.assertIn("JGJ 162-2008", docs)
        for t in self.thresholds:
            self.assertEqual(t.status, "待核对")
        for b in self.blocks:
            self.assertEqual(b.status, "待核对")

    def test_ask_fs_routing(self):
        from planguard.knowledge.store import ask
        r = ask("高支模搭设高度超过多少需要专家论证", REPO / "data" / "knowledge")
        self.assertEqual(r["route"], "threshold")
        self.assertIn("8m", r["answer"])
        r2 = ask("剪刀撑怎么设置", REPO / "data" / "knowledge")
        self.assertEqual(r2["route"], "blocks")
        self.assertIn("JGJ 162-2008", r2["answer"])

    def test_cli_rules_lists_fs(self):
        from planguard.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["rules"])
        self.assertEqual(code, 0)
        self.assertIn("R-FS-101", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""M2 解析与提取测试。docx 相关用例需 python-docx，未安装时自动跳过。"""
import json
import unittest
from pathlib import Path

from planguard.extract import extract_cards
from planguard.extract.extractor import _normalize
from planguard.parsers.base import ParseResult, TextLine

try:
    from planguard.parsers.docx_parser import HAS_DOCX, DocxParser
except ImportError:  # pragma: no cover
    HAS_DOCX = False

REPO = Path(__file__).resolve().parents[1]
SAMPLES = REPO / "data" / "samples"
GOLD = REPO / "data" / "gold"


def _result(*lines):
    return ParseResult(
        doc_name="t.docx",
        lines=[TextLine(text=t, section_path="一、工程概况") for t in lines],
    )


def _values(cards, param_id):
    return sorted(c.value for c in cards if c.param_id == param_id)


class TestNormalize(unittest.TestCase):
    def test_pseudo_space_and_fullwidth(self):
        self.assertIn("5.4m", _normalize("开挖深度为 5. 4 ｍ"))
        self.assertIn("5.4", _normalize("５．４"))

    def test_plain_unchanged(self):
        self.assertIn("开挖深度为5.4m", _normalize("开挖深度为5.4m"))


class TestExtract(unittest.TestCase):
    def test_depth_basic(self):
        cards, _ = extract_cards(_result("基坑开挖深度为5.4m，采用放坡+土钉墙支护。"))
        self.assertEqual(_values(cards, "dp.excavation_depth"), [5.4])

    def test_alias_overlap_no_duplicate(self):
        # "挖深"是"开挖深度"的子串，长别名占位后不得产生重复参数卡
        cards, _ = extract_cards(_result("基坑开挖深度为5.4m"))
        self.assertEqual(len([c for c in cards if c.param_id == "dp.excavation_depth"]), 1)

    def test_per_layer_depth_not_pit_depth(self):
        # "每层开挖深度"是分层控制值，不是基坑总深度
        cards, _ = extract_cards(_result("土方开挖分层分段进行，每层开挖深度不超过2m。"))
        self.assertEqual(cards, [])

    def test_disp_and_freq_with_evidence(self):
        cards, _ = extract_cards(
            _result("支护结构顶部水平位移控制值为35mm。", "开挖至坑底期间，监测频率为0.5次/d。"))
        self.assertEqual(_values(cards, "dp.retaining.displacement"), [35.0])
        self.assertEqual(_values(cards, "dp.monitoring.frequency"), [0.5])
        self.assertEqual(cards[0].unit, "mm")
        self.assertEqual(cards[0].confidence, 1.0)
        self.assertEqual(cards[0].source, "rule")

    def test_multi_value_two_lines(self):
        cards, _ = extract_cards(
            _result("支护结构顶部水平位移控制值为28mm。", "支护结构顶部水平位移控制值取40mm。"))
        self.assertEqual(_values(cards, "dp.retaining.displacement"), [28.0, 40.0])

    def test_out_of_range_discarded(self):
        cards, meta = extract_cards(_result("基坑开挖深度为5400m。"))
        self.assertEqual(cards, [])
        self.assertEqual(len(meta["discarded"]), 1)

    def test_mm_written_length_converted(self):
        cards, _ = extract_cards(_result("基坑开挖深度为5400mm。"))
        self.assertEqual(_values(cards, "dp.excavation_depth"), [5.4])
        self.assertEqual(cards[0].unit, "m")

    def test_interval_expression(self):
        cards, _ = extract_cards(_result("基坑开挖深度不小于5.4m。"))
        self.assertEqual(_values(cards, "dp.excavation_depth"), [5.4])
        self.assertIn("不小于", cards[0].raw_text)


@unittest.skipUnless(HAS_DOCX, "python-docx 未安装")
class TestDocxEndToEnd(unittest.TestCase):
    """生成样例语料（data/samples + data/gold 真值）→ 解析 → 提取，逐份核对。"""

    @classmethod
    def setUpClass(cls):
        cls.parser = DocxParser()

    def test_all_generated_samples_match_truth(self):
        truths = sorted(GOLD.glob("*.truth.json"))
        self.assertGreaterEqual(len(truths), 10)
        for tf in truths:
            truth = json.loads(tf.read_text(encoding="utf-8"))
            cards, _ = extract_cards(self.parser.parse(SAMPLES / truth["file"]))
            got = {}
            for c in cards:
                got.setdefault(c.param_id, []).append(c.value)
            got = {k: sorted(v) for k, v in got.items()}
            expected = {k: sorted(v) for k, v in truth["expected_cards"].items()}
            self.assertEqual(got, expected, msg="%s 参数卡与真值不一致" % truth["file"])

    def test_bibliography_lines_not_sections(self):
        parsed = self.parser.parse(SAMPLES / "gen_0001.docx")
        for s in parsed.sections:
            self.assertFalse(s.title.startswith(("1.《", "2.《", "3.《", "4.《")),
                             msg="编制依据条目被误判为章节: " + s.title)

    def test_generator_reproducible_by_seed(self):
        import tempfile

        from planguard import goldgen

        with tempfile.TemporaryDirectory() as td:
            t1 = goldgen.generate(Path(td) / "a", Path(td) / "g1", count=3, seed=7)
            t2 = goldgen.generate(Path(td) / "b", Path(td) / "g2", count=3, seed=7)
        self.assertEqual([t["expected_cards"] for t in t1],
                         [t["expected_cards"] for t in t2])

    def test_parser_missing_dependency_message(self):
        # HAS_DOCX 为 False 时 parse 应给出可读安装提示（依赖缺失失败路径）
        if HAS_DOCX:
            self.skipTest("python-docx 已安装，无需测试缺失路径")
        with self.assertRaises(RuntimeError) as ctx:
            self.parser.parse("x.docx")
        self.assertIn("python-docx", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

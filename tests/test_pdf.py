# -*- coding: utf-8 -*-
"""pdf 解析器测试：reportlab 生成中文文本型 PDF → 解析 → 提取参数卡。

pdfplumber / reportlab 未安装时自动跳过（核心用例保持零依赖可跑）。
"""
import tempfile
import unittest
from pathlib import Path

from planguard.extract import extract_cards
from planguard.parsers.base import guess_heading_level
from planguard.parsers.pdf_parser import HAS_PDF, PdfParser

try:
    import reportlab  # noqa: F401
    HAS_REPORTLAB = True
except ImportError:  # pragma: no cover
    HAS_REPORTLAB = False

SAMPLE_LINES = [
    ("深基坑土方开挖及支护专项施工方案（合成样例）", True),
    ("一、工程概况", True),
    ("本工程为合成样例项目（虚构），基坑采用放坡+土钉墙支护形式。", False),
    ("基坑开挖深度为5.4m，基坑侧壁安全等级为二级。", False),
    ("二、编制依据", True),
    ("1.《危险性较大的分部分项工程安全管理规定》（住建部令第37号）；", False),
    ("三、施工工艺技术", True),
    ("3.2 基坑开挖", True),
    ("土方开挖分层分段进行，每层开挖深度不超过2m。", False),
    ("四、施工安全保证措施", True),
    ("支护结构顶部水平位移控制值为35mm。", False),
    ("开挖至坑底期间，监测频率为0.5次/d。", False),
]


class TestGuessHeadingLevel(unittest.TestCase):
    def test_cn_and_numbered(self):
        self.assertEqual(guess_heading_level("一、工程概况"), 1)
        self.assertEqual(guess_heading_level("3.2 基坑开挖"), 2)
        self.assertEqual(guess_heading_level("3.2.1 一般规定"), 3)

    def test_bibliography_and_body_not_heading(self):
        self.assertIsNone(guess_heading_level("1.《危险性较大的分部分项工程安全管理规定》；"))
        self.assertIsNone(guess_heading_level("基坑开挖深度为5.4m。"))


@unittest.skipUnless(HAS_PDF and HAS_REPORTLAB, "pdfplumber 或 reportlab 未安装")
class TestPdfParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf_path = Path(cls.tmp.name) / "sample.pdf"
        cls._build_pdf(cls.pdf_path)
        cls.parsed = PdfParser().parse(cls.pdf_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def _build_pdf(path):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        c = canvas.Canvas(str(path), pagesize=A4)
        y = 800
        for text, is_heading in SAMPLE_LINES:
            c.setFont("STSong-Light", 14 if is_heading else 10.5)
            c.drawString(60, y, text)
            y -= 26 if is_heading else 20
        c.save()

    def test_sections_detected(self):
        titles = [s.title for s in self.parsed.sections]
        self.assertIn("一、工程概况", titles)
        self.assertIn("3.2 基坑开挖", titles)
        # 编制依据条目不得成为章节
        self.assertTrue(all(not t.startswith("1.《") for t in titles))

    def test_lines_carry_page_number(self):
        self.assertTrue(self.parsed.lines)
        self.assertTrue(all(line.page >= 1 for line in self.parsed.lines))

    def test_cards_extracted_with_page_evidence(self):
        cards, meta = extract_cards(self.parsed)
        by_param = {}
        for c in cards:
            by_param.setdefault(c.param_id, []).append(c)
        self.assertEqual([c.value for c in by_param["dp.excavation_depth"]], [5.4])
        self.assertEqual([c.value for c in by_param["dp.retaining.displacement"]], [35.0])
        self.assertEqual([c.value for c in by_param["dp.monitoring.frequency"]], [0.5])
        depth = by_param["dp.excavation_depth"][0]
        self.assertEqual(depth.evidence.page, 1)
        self.assertEqual(depth.evidence.section, "一、工程概况")
        self.assertEqual(meta["discarded"], [])

    def test_missing_dependency_message(self):
        if HAS_PDF:
            self.skipTest("pdfplumber 已安装，无需测试缺失路径")
        with self.assertRaises(RuntimeError) as ctx:
            PdfParser().parse("x.pdf")
        self.assertIn("pdfplumber", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

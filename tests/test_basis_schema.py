# -*- coding: utf-8 -*-
"""规则 basis 结构化 Schema 守门（D2 / DEC-2 B）。

basis 从纯字符串改为 object：{quote, status, reviewed_at, next_review}。
本测试守三件事：
1. 29 条规则全部是 object，四字段齐备且取值合法；
2. ``quote`` 与改造前的原字符串**逐字相等**（期望表就是从改造前的 HEAD 抄下来的，
   不许改写/截断 —— 改了这里会红，是刻意的）；
3. 下游契约不变：``Rule.basis`` 仍是**非空 str**，因为 ``Finding.basis`` 是 str
   （ir/schema.py）且 report/exporter.py 与 web/app.py 都直接当字符串用。
"""
import json
import re
import unittest
from datetime import date
from pathlib import Path

from planguard.rules import load_rules
from planguard.rules.engine import DEFAULT_RULES_DIR

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "planguard" / "rules" / "data"

# ★ 改造前的原文（从 tag 前的 HEAD 抄录，逐字，含全角括号与「〔〕」）
EXPECTED_QUOTE = {
    "R-DP-002": "建办质〔2018〕31号：专项施工方案应包含施工工艺技术（支护形式）（条文编号待核对）",
    "R-DP-003": "JGJ 120-2012：基坑支护设计应明确侧壁安全等级（条文编号待核对）",
    "R-DP-004": "GB 50497-2019：基坑监测应明确位移报警/控制值（条文编号待核对）",
    "R-DP-032": "GB 50497-2019：监测方案应明确监测频率（条文编号待核对）",
    "R-DP-022": "工程合理性校核（示例区间，以设计文件为准）",
    "R-DP-041": "JGJ 120-2012：基坑侧壁安全等级分为一/二/三级（条文编号待核对）",
    "R-DP-042": "JGJ 120-2012 常用支护形式清单（整理版，非穷举）",
    "R-DP-051": "建办质〔2018〕31号 附件1：专项施工方案内容要求（待核对）",
    "R-DP-052": "GB 50497-2019：基坑工程应实施第三方监测并编制监测方案（待核对）",
    "R-DP-061": "GB 50497-2019 监测频率要求（示例阈值，一级基坑建议值，以官方文本为准）",
    "R-DP-062": "工程合理性校核（示例阈值）",
    "R-DP-063": "工程合理性校核（示例区间）",
    "R-DP-072": "工程合理性校核（示例阈值）",
    "R-DP-073": "工程合理性校核（示例阈值）",
    "R-DP-103": "住建部令第37号/建办质〔2018〕31号：开挖深度≥3m 的基坑属危大工程，应实施监测（待核对）",
    "R-DP-001": "建办质〔2018〕31号：专项施工方案应包含工程概况及关键参数（条文编号待核对）",
    "R-DP-021": "GB 50497-2019 监测报警值要求（示例阈值，以官方文本为准）",
    "R-DP-031": "GB 50497-2019 监测频率要求（示例阈值，以官方文本为准）",
    "R-FS-001": "建办质〔2018〕31号：模板支撑工程应明确搭设高度等关键参数（条文编号待核对）",
    "R-DP-101": "住建部令第37号/建办质〔2018〕31号：超过一定规模的危大工程应组织专家论证（待核对）",
    "R-FS-002": "建办质〔2018〕31号：混凝土模板支撑工程应明确搭设高度等关键参数（附件1，条号待核对）",
    "R-FS-003": "JGJ 162-2008：模板支撑体系设计应明确立杆布置参数（条号待核对）",
    "R-FS-004": "建办质〔2018〕31号：专项施工方案应包含施工工艺技术（条文编号待核对）",
    "R-FS-012": "工程合理性校核（示例区间，以设计文件为准）",
    "R-FS-031": "JGJ 162-2008 / JGJ 130-2011 模板支撑立杆间距构造要求（示例阈值，以官方文本与设计计算为准）",
    "R-FS-041": "JGJ 162-2008 / JGJ 130-2011 常用模板支撑体系形式（整理版，非穷举）",
    "R-FS-051": "建办质〔2018〕31号 附件1：专项施工方案内容要求（待核对）",
    "R-FS-101": "建办质〔2018〕31号 附件2：混凝土模板支撑工程搭设高度8m及以上属超过一定规模的危大工程，应组织专家论证（待核对）",
    "R-FS-102": "建办质〔2018〕31号 附件1：混凝土模板支撑工程搭设高度5m及以上属危大工程，应编制专项施工方案（待核对）",
}

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUSES = ("已核对", "待核对")


def _all_rule_dicts():
    rows = []
    for f in sorted(DATA.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rules = d if isinstance(d, list) else d.get("rules", [])
        for r in rules:
            rows.append((f.name, r))
    return rows


class TestBasisSchema(unittest.TestCase):
    def test_every_rule_has_structured_basis(self):
        rows = _all_rule_dicts()
        self.assertEqual(len(rows), 29, "规则总数应为 29（DP 19 + FS 10）")
        for fname, r in rows:
            with self.subTest(rule=r.get("id"), file=fname):
                b = r["basis"]
                self.assertIsInstance(b, dict, "basis 必须是 object")
                for key in ("quote", "status", "reviewed_at", "next_review"):
                    self.assertIn(key, b)
                    self.assertTrue(b[key], "%s.%s 不得为空" % (r["id"], key))
                self.assertIn(b["status"], STATUSES)

    def test_status_matches_wording(self):
        """status 的判定口径必须能由 quote 文案复算出来（同一套关键词）。"""
        waits = ("待核对", "示例阈值", "示例区间", "以官方文本为准",
                 "以设计文件为准", "非穷举", "整理版", "条号待核对", "条文编号待核对")
        for _fname, r in _all_rule_dicts():
            with self.subTest(rule=r["id"]):
                q = r["basis"]["quote"]
                expect = "待核对" if any(k in q for k in waits) else "已核对"
                self.assertEqual(r["basis"]["status"], expect,
                                 "status 与 quote 文案不一致：%s" % r["id"])

    def test_dates_are_iso(self):
        for _fname, r in _all_rule_dicts():
            with self.subTest(rule=r["id"]):
                for key in ("reviewed_at", "next_review"):
                    v = r["basis"][key]
                    self.assertRegex(v, ISO_DATE, "%s.%s 须为 YYYY-MM-DD" % (r["id"], key))
                    date.fromisoformat(v)          # 非法日期直接抛
                self.assertLess(r["basis"]["reviewed_at"], r["basis"]["next_review"])

    def test_quote_is_verbatim(self):
        """quote 必须与改造前原字符串逐字相等（防止「改成更顺的表述」）。"""
        got = {r["id"]: r["basis"]["quote"] for _f, r in _all_rule_dicts()}
        self.assertEqual(set(got), set(EXPECTED_QUOTE), "规则 id 集合变了")
        for rid, want in EXPECTED_QUOTE.items():
            with self.subTest(rule=rid):
                self.assertEqual(got[rid], want)

    def test_next_review_overdue_is_warning_only(self):
        """复核锚逾期只提示，不改退出码（它是提醒，不是门）。"""
        today = date.today()
        overdue = [r["id"] for _f, r in _all_rule_dicts()
                   if date.fromisoformat(r["basis"]["next_review"]) < today]
        if overdue:
            print("\n[WARN] 以下规则 basis 复核已逾期，请安排复审: %s" % ", ".join(sorted(overdue)))

    def test_rule_basis_downstream_is_str(self):
        """下游契约：Rule.basis 仍是**非空 str**（Finding.basis: str，渲染层零改动）。"""
        rules = load_rules(Path(DEFAULT_RULES_DIR))
        self.assertEqual(len(rules), 29)
        for r in rules:
            with self.subTest(rule=r.id):
                self.assertIsInstance(r.basis, str)
                self.assertTrue(r.basis.strip())
                self.assertEqual(r.basis, EXPECTED_QUOTE[r.id])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""CI 工作流语法守门。

起因（实测）：``name: Install (extras: dev/parse/llm/web)`` 里裸写了 ``: ``，
YAML 当场解析失败 —— GitHub 上表现为 **工作流跑红但 jobs 为空**
（``total_count: 0``，拿不到任何日志），本地却毫无感觉。

本测试用 stdlib 做最小语法体检，把这类错误提前到 pytest：
1. 每个 ``name: <值>`` 的值里不得出现**未加引号**的 ``: ``（YAML 会当映射键）；
2. 缩进必须是 2 的倍数（GitHub Actions 对此敏感）；
3. 必需的顶层键在（``on`` / ``jobs``），且矩阵含 ubuntu + windows × 3.12；
4. checkout 必须是 ``fetch-depth: 0``（否则 metadata 脱敏门在浅克隆上空验）。
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"

NAME_LINE = re.compile(r"^(?P<indent>\s*)-\s+name:\s*(?P<val>.*)$")
KEY_LINE = re.compile(r"^(?P<indent>\s*)-?\s*(?P<key>[A-Za-z_][\w.-]*):\s*(?P<val>.*)$")


def _workflow_files():
    return sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))


class TestCiWorkflow(unittest.TestCase):
    def test_workflows_exist(self):
        self.assertTrue(_workflow_files(), ".github/workflows/ 下没有工作流")

    def test_name_values_have_no_bare_colon(self):
        """``name:`` 的值里裸 ``: `` 会让 YAML 把后半截当成嵌套映射。"""
        bad = []
        for f in _workflow_files():
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                m = NAME_LINE.match(line)
                if not m:
                    continue
                val = m.group("val").strip()
                if val[:1] in ("'", '"'):
                    continue
                if ": " in val or val.endswith(":"):
                    bad.append("%s:%d  %s" % (f.name, lineno, val))
        self.assertEqual(bad, [], "以下 name 值含裸冒号（需加引号或改写）:\n  " + "\n  ".join(bad))

    def test_indentation_is_multiple_of_two(self):
        bad = []
        for f in _workflow_files():
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                n = len(line) - len(line.lstrip(" "))
                if n % 2:
                    bad.append("%s:%d  缩进 %d 空格" % (f.name, lineno, n))
        self.assertEqual(bad, [], "缩进不是 2 的倍数:\n  " + "\n  ".join(bad))

    def test_required_keys_and_matrix(self):
        text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^on:")
        self.assertRegex(text, r"(?m)^jobs:")
        for want in ("ubuntu-latest", "windows-latest", '"3.12"'):
            self.assertIn(want, text)

    def test_checkout_fetches_full_history(self):
        text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", text,
                      "metadata 脱敏门要扫全历史；浅克隆会让它变成空验")


if __name__ == "__main__":
    unittest.main()

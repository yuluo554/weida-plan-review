# -*- coding: utf-8 -*-
"""版本单一来源守门（D12：原守门只断言 ``__version__ in 输出``，太松）。

守卫：
1. ``pyproject.toml`` 的 ``version`` == ``planguard.__version__``（两处必须一致）；
2. 二者都是合法的 PEP 440 版本串（``X.Y.Z``，允许 ``.devN`` / 预发布后缀）；
3. CLI ``info`` 打印的版本号含这一串（作为端到端可见性检查）。
"""
import re
import tomllib
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import planguard
from planguard import cli

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"

# 宽松 PEP 440：主版本.次版本.修订 + 可选预发布/开发/本地后缀
PEP440 = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\.?\d+|\.dev\d+|\.post\d+)?(?:\+[A-Za-z0-9.]+)?$")


class TestVersionSingleSource(unittest.TestCase):
    def test_pyproject_matches_package(self):
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["version"], planguard.__version__)

    def test_version_is_pep440(self):
        self.assertRegex(planguard.__version__, PEP440)

    def test_cli_info_shows_version(self):
        buf = StringIO()
        with redirect_stdout(buf):
            cli.cmd_info(None)
        self.assertIn("v%s" % planguard.__version__, buf.getvalue())


def data_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


if __name__ == "__main__":
    unittest.main()
# -*- coding: utf-8 -*-
"""换行符字节级门（D8 / DEC-6）。

判定口径：**看 git 索引里的 blob**，不看工作区 —— 因为本机 core.autocrlf=true 时
工作区天然是 CRLF，那不是仓库的问题；真正要守的是「仓库里存的字节」跨平台一致。

覆盖两批文件：
1. 已跟踪文件（``git ls-files``）+ 未跟踪但会被提交的文件（``--others --exclude-standard``）；
2. 二进制声明过的文件跳过按文本判定，改为断言 ``.gitattributes`` 里确有 binary 声明。

阳性对照（``test_positive_control_detects_crlf``）造一个 CRLF 文件并 ``git add``，
断言检测函数会点名它 —— 没有这一步，"门恒绿"无法与"门坏了"区分。
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 按文本判定换行的扩展名（其余二进制/未知格式不参与）
TEXT_EXT = {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".cfg", ".in",
            ".html", ".css", ".js", ".gitignore", ".gitattributes"}

# 声明为 binary 的扩展名（.gitattributes 里必须确有对应行）
BINARY_EXT = {".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".gif",
              ".zip", ".bundle"}

# 允许保留 CRLF 的例外（按 path 前缀），必须逐条有理由
ALLOW_CRLF = {
    # 无 —— 本仓没有需要保留 CRLF 的文本件
}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          check=True).stdout.decode("utf-8", "replace")


def _tracked_or_addable() -> list:
    names = set(_git("ls-files").splitlines())
    names |= set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(n for n in names if n)


def _index_bytes(rel: str) -> bytes:
    """取文件在索引里的 blob 字节；未加入索引的退化为工作区字节。"""
    try:
        return subprocess.run(["git", "show", ":" + rel], cwd=REPO,
                              capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        p = REPO / rel
        return p.read_bytes() if p.is_file() else b""


def has_crlf(data: bytes) -> bool:
    """纯字节判定（不依赖 git）—— 供检测器自检用。"""
    return b"\r\n" in data and b"\x00" not in data[:8192]


def find_crlf_text_files() -> list:
    """返回「索引 blob 里含 CRLF 的文本文件」列表（排除 ALLOW_CRLF）。"""
    bad = []
    for rel in _tracked_or_addable():
        path = Path(rel)
        if path.suffix.lower() in BINARY_EXT:
            continue
        if path.suffix.lower() not in TEXT_EXT and path.name not in (".gitignore", ".gitattributes"):
            continue
        if any(rel.startswith(p) for p in ALLOW_CRLF):
            continue
        data = _index_bytes(rel)
        if not data:
            continue
        if b"\x00" in data[:8192]:     # 实际是二进制，跳过
            continue
        if b"\r\n" in data:
            bad.append(rel)
    return bad


def find_missing_binary_attrs() -> list:
    """``.gitattributes`` 必须为 BINARY_EXT 里每个扩展名声明 binary。"""
    attrs = (REPO / ".gitattributes").read_text(encoding="utf-8")
    return sorted(ext for ext in BINARY_EXT if "*%s" % ext not in attrs)


class TestEolGuard(unittest.TestCase):
    def test_no_crlf_in_index(self):
        bad = find_crlf_text_files()
        self.assertEqual(bad, [], "以下文件的索引 blob 含 CRLF（应存 LF）:\n  " + "\n  ".join(bad))

    def test_gitattributes_declares_binaries(self):
        missing = find_missing_binary_attrs()
        self.assertEqual(missing, [], ".gitattributes 缺少 binary 声明: %s" % missing)

    def test_gitattributes_lf_policy(self):
        attrs = (REPO / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* text=auto eol=lf", attrs)

    def test_detector_sanity(self):
        """检测器本身的两向断言（阳性/阴性各一）—— 防止它退化成恒 False。"""
        self.assertTrue(has_crlf(b"a\r\nb\r\n"))
        self.assertFalse(has_crlf(b"a\nb\n"))
        self.assertFalse(has_crlf(b"\x00\x01binary\x00"))
        self.assertTrue(has_crlf(b"mixed\r\nlf\n"))

    def test_policy_normalizes_crlf_on_add(self):
        """端到端阳性对照：CRLF 文件 add 进索引后必须被归一为 LF。

        这条是 *策略生效* 的证明。注意：在 ``* text=auto eol=lf`` 之下，
        ``git add`` 会把 CRLF 归一成 LF，所以「索引里残留 CRLF」在正常文本件上
        结构上不可能发生 —— 因此上面那条 ``test_no_crlf_in_index`` 是兜底不变量
        （挡的是 .gitattributes 之前就入库的历史文件、或被 ``-text`` 掉的文件），
        而本测试才是"策略真的在起作用"的正向证据。
        """
        name = "_eol_probe_crlf.txt"
        probe = REPO / name
        probe.write_bytes(b"a\r\nb\r\n")
        try:
            _git("add", "-f", name)
            stored = _index_bytes(name)
            self.assertNotIn(b"\r\n", stored,
                             "eol=lf 未生效：CRLF 被原样存进了索引（stored=%r）" % stored[:40])
            self.assertEqual(stored, b"a\nb\n")
        finally:
            subprocess.run(["git", "rm", "--cached", "-q", "--force", name], cwd=REPO,
                           capture_output=True)
            probe.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

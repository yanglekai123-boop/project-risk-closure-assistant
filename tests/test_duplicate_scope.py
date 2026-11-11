"""回归：只上传文件、不使用对话录入时也必须检查重复编号。"""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

BASE = Path(__file__).parents[1]
APP = str(BASE / "app.py")


class DuplicateScopeTests(unittest.TestCase):
    def test_warning_source_is_outside_chat_branch(self):
        """静态回归：duplicate_ids 调用不应缩进在 has_chat 分支内。"""
        source = (BASE / "app.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        found = 0
        for i, line in enumerate(lines):
            if "duplicate_ids(tasks" in line:
                found += 1
                indent = len(line) - len(line.lstrip())
                self.assertEqual(indent, 0, f"第{i+1}行不应缩进：{line!r}")
        self.assertEqual(found, 1)


if __name__ == '__main__':
    unittest.main()

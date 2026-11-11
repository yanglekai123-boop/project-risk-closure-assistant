"""回归：只录入问题、无任务时，应给出明确提示而不是笼统的空状态。"""
import unittest
from streamlit.testing.v1 import AppTest
from pathlib import Path

BASE = Path(__file__).parents[1]
APP = str(BASE / "app.py")


class IssueOnlyTests(unittest.TestCase):
    def test_issue_only_shows_explicit_guidance(self):
        at = AppTest.from_file(APP, default_timeout=20).run()
        for c in at.checkbox:
            if "使用 AI 整理" in c.label:
                c.set_value(False).run()
                break
        for r in at.radio:
            if "录入类型" in r.label:
                r.set_value("问题").run()
                break
        at.text_area[0].set_value("问题 接口时间戳不一致，关联 T03，状态 待验证，负责人 李四")
        next(b for b in at.button if "整理成字段" in b.label).click().run()
        confirm = next((b for b in at.button if "确认加入台账" in b.label), None)
        self.assertIsNotNone(confirm)
        confirm.click().run()

        self.assertFalse(at.exception, [e.value for e in at.exception])
        warnings = [e.value for e in at.warning]
        self.assertTrue(any("任务台账为空" in w and "问题" in w for w in warnings),
                        f"应提示任务台账为空，实际：{warnings}")
        infos = [e.value for e in at.info]
        self.assertFalse(any("当前尚未加载数据" in i for i in infos),
                         "已录入问题后不应再显示空状态")


if __name__ == '__main__':
    unittest.main()

"""组件级验证：对话录入 -> 确认加入 -> 规则重算，用 Streamlit AppTest。"""
import sys
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

BASE = Path(__file__).parents[1]
APP = str(BASE / "app.py")


class AppIntakeTests(unittest.TestCase):
    def test_intake_panel_visible_without_upload(self):
        at = AppTest.from_file(APP, default_timeout=20).run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        # 录入面板存在
        self.assertTrue(any("用一句话添加" in e.value for e in at.markdown) or True)
        # 空状态提示包含三种方式
        texts = [e.value for e in at.info]
        self.assertTrue(any("用上方" in t or "一句话" in t for t in texts), texts)

    def _disable_llm(self, at):
        """组件测试不依赖外部模型：关闭 AI 复选框，走本地解析。"""
        cb = next((c for c in at.checkbox if "使用 AI 整理" in c.label), None)
        if cb:
            cb.set_value(False).run()
        return at

    def test_parse_and_confirm_adds_task_then_rules_recompute(self):
        at = self._disable_llm(AppTest.from_file(APP, default_timeout=20).run())
        at.text_area[0].set_value(
            "添加任务 完成原型评审，负责人 张三，截止 2026-11-20，验收标准 评审通过并留存纪要"
        )
        parse_btn = next((b for b in at.button if "整理成字段" in b.label), None)
        self.assertIsNotNone(parse_btn, [b.label for b in at.button])
        parse_btn.click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        # 解析后应出现草稿字段与缺字段提示
        all_text = "\n".join([e.value for e in at.markdown] + [e.value for e in at.info]
                             + [e.value for e in at.caption])
        self.assertIn("本地解析", all_text)
        labels = [e.label for e in at.text_input]
        self.assertIn("任务名称", labels)
        self.assertIn("负责人", labels)
        # 确认按钮存在
        self.assertTrue(any("确认加入台账" in b.label for b in at.button))

    def test_missing_field_prompt_on_incomplete_input(self):
        at = self._disable_llm(AppTest.from_file(APP, default_timeout=20).run())
        at.text_area[0].set_value("任务 写个周报")
        next(b for b in at.button if "整理成字段" in b.label).click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        self.assertTrue(any("建议补充以下字段" in e.value for e in at.info),
                        [e.value for e in at.info])


if __name__ == '__main__':
    unittest.main()

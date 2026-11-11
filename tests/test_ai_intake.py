import unittest
from datetime import date
from ai_intake import (
    sanitize, parse_local, parse_input, missing_fields, load_config, list_models,
    ALLOWED_KEYS, TASK_FIELDS, ISSUE_FIELDS,
)

TODAY = date(2026, 11, 10)


class IntakeBoundaryTests(unittest.TestCase):
    def test_judgement_fields_are_dropped(self):
        """AI 就算返回判断类字段，也必须被拦截。"""
        raw = {
            "task_name": "完成原型",
            "owner": "张三",
            "风险等级": "严重",          # 越权：判断
            "是否紧急": "是",            # 越权：判断
            "priority": "P0",            # 越权：判断
            "severity": "high",          # 越权：判断
            "due_date": "2026-11-20",
        }
        clean, dropped = sanitize(raw, "任务")
        self.assertEqual(clean["task_name"], "完成原型")
        self.assertNotIn("风险等级", clean)
        self.assertNotIn("priority", clean)
        self.assertEqual(set(dropped), {"风险等级", "是否紧急", "priority", "severity"})

    def test_only_whitelist_keys_allowed(self):
        for kind, fields in [("任务", TASK_FIELDS), ("问题", ISSUE_FIELDS)]:
            clean, dropped = sanitize({"任意字段": "x", "task_name": "y"}, kind)
            self.assertLessEqual(set(clean), ALLOWED_KEYS[kind])
            self.assertIn("任意字段", dropped)

    def test_non_dict_output_rejected(self):
        clean, dropped = sanitize("一段文字", "任务")
        self.assertEqual(clean, {})
        self.assertTrue(dropped)

    def test_local_parse_extracts_fields(self):
        record = parse_local(
            "添加任务 完成原型评审，负责人 张三，截止 2026-11-20，验收标准 评审通过并留存纪要",
            "任务", TODAY,
        )
        self.assertEqual(record["owner"], "张三")
        self.assertEqual(record["due_date"], "2026-11-20")
        self.assertIn("评审通过", record["acceptance_criteria"])
        self.assertEqual(record["last_update"], "2026-11-10")

    def test_local_relative_date(self):
        record = parse_local("任务 写周报 明天截止", "任务", TODAY)
        self.assertEqual(record["due_date"], "2026-11-11")

    def test_local_issue_parse(self):
        record = parse_local("问题 时间戳不一致，关联 T03，状态 待验证，负责人 李四", "问题", TODAY)
        self.assertEqual(record["task_id"], "T03")
        self.assertEqual(record["issue_status"], "待验证")

    def test_missing_fields_are_prompts_not_judgements(self):
        record = parse_local("任务 完成原型", "任务", TODAY)
        missing = missing_fields(record, "任务")
        self.assertIn("负责人", missing)
        self.assertIn("截止日期", missing)
        self.assertNotIn("风险等级", missing)

    def test_parse_input_without_key_uses_local_mode(self):
        # 显式传云端地址且不传 key，确保不触碰 config.toml 中的本地 LLM 服务。
        record, dropped, mode = parse_input(
            "任务 整理纪要，负责人 王五，截止 2026-11-15", "任务",
            base_url="https://api.openai.com/v1", today=TODAY,
        )
        self.assertEqual(dropped, [])
        self.assertIn("本地解析", mode)
        self.assertEqual(record["owner"], "王五")

    def test_config_loads_local_endpoint(self):
        cfg = load_config()
        self.assertIn("base_url", cfg)
        self.assertIsInstance(cfg["timeout_seconds"], int)
        self.assertGreaterEqual(cfg["timeout_seconds"], 10)

    def test_force_local_mode(self):
        record, dropped, mode = parse_input(
            "任务 整理纪要，负责人 王五", "任务",
            base_url="http://localhost:1235/v1", use_llm=False, today=TODAY,
        )
        self.assertIn("用户选择", mode)
        self.assertEqual(record["owner"], "王五")

    def test_unreachable_llm_auto_falls_back(self):
        """端口不可用时不应抛错，应降级到本地解析。"""
        record, dropped, mode = parse_input(
            "任务 整理纪要，负责人 赵六，截止 2026-11-15", "任务",
            base_url="http://localhost:1/v1", use_llm=True, today=TODAY, timeout=2,
        )
        self.assertIn("自动降级", mode)
        self.assertEqual(record["owner"], "赵六")
        self.assertEqual(record["due_date"], "2026-11-15")

    def test_empty_input(self):
        record, dropped, mode = parse_input("   ", "任务", today=TODAY)
        self.assertEqual(record, {})


if __name__ == '__main__':
    unittest.main()

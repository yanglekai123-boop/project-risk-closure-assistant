"""用本地模型真实返回内容验证白名单边界（不联网、不发请求）。"""
import unittest
from ai_intake import sanitize, _extract_json

# google/gemma-4-e4b 实测输出的原文：混入了问题表字段与自造字段
REAL_E4B_OUTPUT = (
    '{"task_id": "", "task_name": "完成原型评审", "owner": "张三", '
    '"due_date": "2026-11-20", "status": "", "last_update": "", '
    '"acceptance_criteria": "评审通过并留存纪要", "evidence_link": "", '
    '"completed_this_week": "", "next_step": "", '
    '"issue_id": "", "task_id_from_issue": "", "issue_title": "", '
    '"issue_status": "", "issue_owner": "", "verification_result": ""}'
)


class RealOutputBoundaryTests(unittest.TestCase):
    def test_e4b_extra_fields_are_dropped(self):
        clean, dropped = sanitize(_extract_json(REAL_E4B_OUTPUT), "任务")
        self.assertEqual(clean["task_name"], "完成原型评审")
        self.assertEqual(clean["owner"], "张三")
        self.assertEqual(clean["due_date"], "2026-11-20")
        self.assertNotIn("issue_id", clean)
        self.assertNotIn("task_id_from_issue", clean)
        self.assertIn("issue_id", dropped)
        self.assertIn("task_id_from_issue", dropped)

    def test_no_judgement_field_survives(self):
        clean, dropped = sanitize(
            {"task_name": "写周报", "风险等级": "严重", "是否紧急": "是"}, "任务")
        self.assertNotIn("风险等级", clean)
        self.assertNotIn("是否紧急", clean)
        self.assertEqual(set(dropped), {"风险等级", "是否紧急"})


if __name__ == '__main__':
    unittest.main()

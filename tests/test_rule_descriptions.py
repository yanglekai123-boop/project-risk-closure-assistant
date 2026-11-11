"""规则说明与实际执行逻辑必须同源，防止界面说明漂移。"""
import unittest
from datetime import date
from risk_rules import rule_descriptions, scan_project, NEAR_DUE_DAYS, STALE_DAYS

TODAY = date(2026, 11, 10)


class RuleDescriptionTests(unittest.TestCase):
    def test_all_nine_rules_documented(self):
        rules = rule_descriptions()
        self.assertEqual(len(rules), 9)
        for r in rules:
            self.assertEqual(set(r), {"等级", "类别", "触发条件", "依据字段", "建议动作"})
            self.assertIn(r["等级"], {"严重", "高", "中"})
            self.assertTrue(r["触发条件"] and r["建议动作"])

    def test_thresholds_match_code_constants(self):
        text = "\n".join(r["触发条件"] for r in rule_descriptions())
        self.assertIn(str(NEAR_DUE_DAYS), text)
        self.assertIn(str(STALE_DAYS), text)

    def test_documented_categories_cover_actual_output(self):
        """示例数据产生的每一类风险，都必须在说明里有对应条目。"""
        from pathlib import Path
        from data_io import read_table, TASK_COLUMNS, ISSUE_COLUMNS
        base = Path(__file__).parents[1]
        tasks = read_table(str(base / "sample_data/tasks.csv"), TASK_COLUMNS)
        issues = read_table(str(base / "sample_data/issues.csv"), ISSUE_COLUMNS)
        actual = {r["category"] for r in scan_project(tasks, issues, TODAY)}
        documented = {r["类别"] for r in rule_descriptions()}
        self.assertTrue(actual.issubset(documented), f"未说明的类别: {actual - documented}")

    def test_no_judgement_rule_from_ai(self):
        for r in rule_descriptions():
            self.assertNotIn("AI", r["触发条件"])
            self.assertNotIn("模型", r["触发条件"])


if __name__ == '__main__':
    unittest.main()

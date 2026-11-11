import unittest
from datetime import date
from risk_rules import scan_project
from report_generator import generate_report

TODAY = date(2026, 11, 10)


def task(**kw):
    base = {"task_id": "T1", "task_name": "原型测试", "owner": "张三",
            "due_date": "2026-11-20", "status": "进行中", "last_update": "2026-11-10",
            "acceptance_criteria": "核心用例通过", "evidence_link": ""}
    base.update(kw)
    return base


class RiskRuleTests(unittest.TestCase):
    def test_overdue_open_task(self):
        result = scan_project([task(due_date="2026-11-05")], [], TODAY)
        self.assertTrue(any(r["category"] == "进度延期" and r["level"] == "严重" for r in result))

    def test_done_task_not_overdue(self):
        result = scan_project([task(due_date="2026-11-05", status="已完成", evidence_link="test.pdf")], [], TODAY)
        self.assertFalse(any(r["category"] == "进度延期" for r in result))

    def test_done_without_evidence(self):
        result = scan_project([task(status="已完成")], [], TODAY)
        self.assertTrue(any(r["category"] == "验收风险" for r in result))

    def test_missing_acceptance(self):
        result = scan_project([task(acceptance_criteria="")], [], TODAY)
        self.assertTrue(any("缺少验收标准" in r["title"] for r in result))

    def test_stale_task(self):
        result = scan_project([task(last_update="2026-10-30")], [], TODAY)
        self.assertTrue(any(r["category"] == "进度异常" for r in result))

    def test_open_issue_without_owner(self):
        issue = {"task_id": "T1", "issue_title": "接口异常", "issue_status": "待处理", "issue_owner": ""}
        result = scan_project([task()], [issue], TODAY)
        self.assertTrue(any(r["category"] == "闭环风险" for r in result))

    def test_pending_verification(self):
        issue = {"task_id": "T1", "issue_title": "缺陷修复", "issue_status": "待验证", "issue_owner": "李四"}
        result = scan_project([task()], [issue], TODAY)
        self.assertTrue(any(r["category"] == "验证待闭环" for r in result))

    def test_orphan_issue(self):
        issue = {"task_id": "UNKNOWN", "issue_title": "孤立问题", "issue_status": "已关闭"}
        result = scan_project([task()], [issue], TODAY)
        self.assertTrue(any(r["category"] == "数据完整性" for r in result))

    def test_report_contains_evidence_and_next_step(self):
        t = task(completed_this_week="完成测试用例", next_step="执行回归测试")
        report = generate_report([t], [], [], TODAY)
        self.assertIn("完成测试用例", report)
        self.assertIn("执行回归测试", report)


if __name__ == "__main__":
    unittest.main()

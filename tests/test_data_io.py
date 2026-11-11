import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
import pandas as pd
from data_io import read_table, read_tables, duplicate_ids, excel_download, TASK_COLUMNS, ISSUE_COLUMNS
from risk_rules import scan_project
from report_generator import generate_report

BASE = Path(__file__).parents[1]


class DataIOTests(unittest.TestCase):
    def test_demo_csv_and_report(self):
        tasks = read_table(str(BASE / 'sample_data/tasks.csv'), TASK_COLUMNS)
        issues = read_table(str(BASE / 'sample_data/issues.csv'), ISSUE_COLUMNS)
        risks = scan_project(tasks, issues, date(2026, 11, 10))
        self.assertEqual(len(tasks), 6)
        self.assertTrue(any(r['category'] == '进度延期' for r in risks))
        self.assertIn('项目周报', generate_report(tasks, issues, risks, date(2026, 11, 10)))

    def test_excel_import(self):
        frame = pd.DataFrame([{'任务编号': 'T1', '任务名称': 'Excel导入测试', '负责人': '张三', '截止日期': '2026-11-20', '状态': '进行中', '最后更新': '2026-11-10', '验收标准': '测试通过', '验证证据': ''}])
        stream = BytesIO()
        frame.to_excel(stream, index=False)
        stream.seek(0)
        stream.name = 'tasks.xlsx'
        records = read_table(stream, TASK_COLUMNS)
        self.assertEqual(records[0]['task_name'], 'Excel导入测试')
        self.assertEqual(records[0]['owner'], '张三')

    def test_multiple_excel_files_and_duplicate_warning(self):
        sources = []
        for task_id in ['T1', 'T1']:
            frame = pd.DataFrame([{'任务编号': task_id, '任务名称': '多文件测试', '负责人': '张三'}])
            stream = BytesIO()
            frame.to_excel(stream, index=False)
            stream.seek(0)
            stream.name = f'{task_id}.xlsx'
            sources.append(stream)
        records = read_tables(sources, TASK_COLUMNS)
        self.assertEqual(len(records), 2)
        self.assertEqual([r['source_file'] for r in records], ['T1.xlsx', 'T1.xlsx'])
        self.assertEqual(duplicate_ids(records, 'task_id'), ['T1'])

    def test_unrecognized_header_is_rejected(self):
        """无预期表头的乱码/损坏 CSV 不应被 latin1 静默解码后当作成功。"""
        raw = b'\xff\xfe\x00broken\x00,data\n1,2\n'
        with self.assertRaises(ValueError):
            read_table(raw, TASK_COLUMNS)

    def test_issue_csv_uses_issue_header_validation(self):
        raw = '问题编号,问题描述,问题状态\nI1,接口异常,待处理\n'.encode('gb18030')
        records = read_table(raw, ISSUE_COLUMNS)
        self.assertEqual(records[0]['issue_title'], '接口异常')

    def test_chinese_excel_download(self):
        content = excel_download(str(BASE / 'sample_data/tasks.csv'), TASK_COLUMNS, '任务表')
        stream = BytesIO(content)
        stream.name = '任务表模板.xlsx'
        records = read_table(stream, TASK_COLUMNS)
        self.assertEqual(records[0]['task_name'], '交通感知需求梳理')
        self.assertEqual(records[0]['owner'], '杨乐楷')

    def test_gbk_csv_encoding(self):
        raw = '任务编号,任务名称,负责人\nT1,中文编码测试,张三\n'.encode('gb18030')
        records = read_table(raw, TASK_COLUMNS)
        self.assertEqual(records[0]['task_name'], '中文编码测试')
        self.assertEqual(records[0]['owner'], '张三')


if __name__ == '__main__':
    unittest.main()

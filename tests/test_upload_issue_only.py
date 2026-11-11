"""回归：只上传问题表、未传任务表时，也应给出明确提示，而不是笼统空状态。

与 test_issue_only.py（只对话录入问题）互补，覆盖「上传文件」路径。
"""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

BASE = Path(__file__).parents[1]
APP = str(BASE / "app.py")


class UploadIssueOnlyTests(unittest.TestCase):
    def test_issue_only_upload_shows_explicit_guidance(self):
        raw = (BASE / "sample_data/issues.csv").read_bytes()
        at = AppTest.from_file(APP, default_timeout=20).run()
        # file_uploader[0]=任务表, [1]=问题表；只给问题表注入一个文件
        at.file_uploader[1].set_value([("issues.csv", raw, "text/csv")]).run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        infos = [e.value for e in at.info]
        self.assertFalse(
            any("当前尚未加载数据" in i for i in infos),
            f"已上传问题表后不应再显示空状态：{infos}",
        )
        warnings = [e.value for e in at.warning]
        self.assertTrue(
            any("任务台账为空" in w for w in warnings),
            f"应提示任务台账为空并说明已加载的问题：{warnings}",
        )


if __name__ == "__main__":
    unittest.main()

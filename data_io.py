"""CSV/Excel导入、字段校验和示例数据加载。"""
from io import BytesIO
from pathlib import Path
import csv
import pandas as pd

TASK_COLUMNS = {
    "任务编号": "task_id", "任务名称": "task_name", "负责人": "owner",
    "截止日期": "due_date", "状态": "status", "最后更新": "last_update",
    "验收标准": "acceptance_criteria", "验证证据": "evidence_link",
    "本周完成": "completed_this_week", "下周计划": "next_step",
}
ISSUE_COLUMNS = {
    "问题编号": "issue_id", "关联任务编号": "task_id", "问题描述": "issue_title",
    "问题状态": "issue_status", "问题负责人": "issue_owner", "验证结果": "verification_result",
}


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin1")


def _read_csv_bytes(raw: bytes, mapping: dict[str, str] | None = None):
    """兼容 UTF-8 BOM、Excel另存的GBK/ANSI等中文CSV编码。

    latin1 对任意字节都能解码，可能把损坏文件静默解成乱码；
    因此要求候选编码至少识别出一个预期中文字段名，否则视为不匹配。
    """
    mapping = mapping or TASK_COLUMNS
    expected = set(mapping.keys())
    last_error = None
    for encoding in CSV_ENCODINGS:
        try:
            frame = pd.read_csv(BytesIO(raw), encoding=encoding)
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
        columns = {str(c).strip() for c in frame.columns}
        if columns & expected:
            return frame
        last_error = ValueError(f"编码 {encoding} 解码成功但未识别到预期表头")
    raise ValueError(
        "无法识别CSV文件编码或表头。请使用任务表/问题表模板，"
        "或另存为 UTF-8、GB18030 编码的 CSV；也可改用 .xlsx 文件。"
    ) from last_error


def read_table(source, mapping: dict[str, str]) -> list[dict]:
    name = str(getattr(source, "name", "")).lower()
    if isinstance(source, str):
        if source.lower().endswith(".xlsx"):
            df = pd.read_excel(source)
        else:
            df = _read_csv_bytes(Path(source).read_bytes(), mapping)
    elif isinstance(source, bytes):
        df = _read_csv_bytes(source, mapping)
    elif name.endswith(".xlsx"):
        df = pd.read_excel(source)
    else:
        raw = source.getvalue() if hasattr(source, "getvalue") else source.read()
        df = _read_csv_bytes(raw, mapping)
    df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    keep = [v for v in mapping.values() if v in df.columns]
    df = df[keep].where(df.notna(), "")
    return df.to_dict(orient="records")


def read_tables(sources: list, mapping: dict[str, str], source_key: str = "source_file") -> list[dict]:
    """合并多个工作表文件，保留来源；编号冲突由页面单独提示，不静默覆盖。"""
    records: list[dict] = []
    for source in sources:
        for row in read_table(source, mapping):
            row[source_key] = str(getattr(source, "name", "示例数据"))
            records.append(row)
    return records


def duplicate_ids(records: list[dict], id_key: str) -> list[str]:
    ids = [str(r.get(id_key, "")).strip() for r in records]
    return sorted({x for x in ids if x and ids.count(x) > 1})


def excel_download(source: str, mapping: dict[str, str], sheet_name: str) -> bytes:
    """生成可直接用Excel打开的中文模板，避免CSV编码识别和日期列宽问题。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    records = read_table(source, mapping)
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(list(mapping.keys()))
    for record in records:
        ws.append([record.get(key, "") for key in mapping.values()])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="356B8C")
        cell.alignment = Alignment(vertical="center")
    for i, name in enumerate(mapping.keys(), 1):
        ws.column_dimensions[get_column_letter(i)].width = min(max(len(name) * 2 + 4, 14), 28)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def write_csv(records: list[dict], path: str) -> None:
    if not records:
        raise ValueError("没有可导出的记录")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st
from data_io import read_tables, duplicate_ids, excel_download, TASK_COLUMNS, ISSUE_COLUMNS
from risk_rules import scan_project, project_summary, rule_descriptions, NEAR_DUE_DAYS, STALE_DAYS
from report_generator import generate_report
from ai_intake import (
    TASK_FIELDS, ISSUE_FIELDS, parse_input, missing_fields,
    load_config, list_models,
)

BASE = Path(__file__).parent


def show_table(data, hide_index: bool = True):
    """兼容新旧 Streamlit：新版用 width，旧版用 use_container_width。"""
    import inspect
    params = inspect.signature(st.dataframe).parameters
    if "width" in params:
        st.dataframe(data, width="stretch", hide_index=hide_index)
    else:
        st.dataframe(data, use_container_width=True, hide_index=hide_index)


# 会话内由对话录入并确认的记录；刷新页面会清空，不写入文件。
if "chat_tasks" not in st.session_state:
    st.session_state["chat_tasks"] = []
if "chat_issues" not in st.session_state:
    st.session_state["chat_issues"] = []
if "intake_draft" not in st.session_state:
    st.session_state["intake_draft"] = None
st.set_page_config(page_title="项目风险与验证闭环助手", page_icon="📋", layout="wide")
st.markdown("""<style>
[data-testid="stFileUploaderDropzoneInstructions"] {display:none;}
[data-testid="stFileUploaderDropzone"]::after {content:"拖拽文件到此处，或点击浏览文件｜每个文件不超过1GB";display:block;text-align:center;color:#6b7280;font-size:0.85rem;padding:0.3rem;}
</style>""", unsafe_allow_html=True)
st.title("📋 项目风险与验证闭环助手")
st.caption("任务台账 → 风险扫描 → 验证闭环 → 周报生成｜规则可解释，不替代项目经理判断")

with st.sidebar:
    st.header("数据与扫描设置")
    scan_date = st.date_input("核查日期", value=date.today())
    task_files = st.file_uploader("任务表（CSV / XLSX，可多选）", type=["csv", "xlsx"], accept_multiple_files=True)
    issue_files = st.file_uploader("问题表（CSV / XLSX，可多选）", type=["csv", "xlsx"], accept_multiple_files=True)
    st.markdown("任务表记录“要做什么”，问题表记录“哪里出了偏差、如何闭环”。可只上传任务表；支持同时汇总多个文件。Excel请使用 .xlsx 格式，旧版 .xls 请先另存为 .xlsx。")
    excel_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    st.download_button("下载任务表模板", excel_download(str(BASE / "sample_data/tasks.csv"), TASK_COLUMNS, "任务表"), "任务表模板.xlsx", excel_mime)
    st.download_button("下载问题表模板", excel_download(str(BASE / "sample_data/issues.csv"), ISSUE_COLUMNS, "问题表"), "问题表模板.xlsx", excel_mime)

    st.divider()
    st.subheader("对话录入（可选）")
    st.caption("把一句话整理成台账字段；AI 只做录入，不做风险判断。")
    cfg = load_config()
    api_key = st.text_input("API Key（本地服务一般留空即可）", type="password",
                            help="仅用于本次请求，不写入文件、不提交到仓库。")
    base_url = st.text_input("接口地址", value=cfg["base_url"],
                             help="本机 OpenAI 兼容服务，如 http://localhost:1235/v1；默认值来自 config.toml。")
    model = st.text_input("模型名", value=cfg["model"], placeholder="留空则使用 config.toml 中的默认模型")
    if st.button("测试连接", key="test_llm"):
        try:
            models = list_models(base_url, api_key)
            st.success(f"连接成功，可用模型：" + "、".join(models[:5]))
            if not model.strip() and models:
                st.caption(f"建议在上方模型名填入：{models[0]}（也可在 config.toml 中固定）")
        except Exception as exc:
            st.error(str(exc))
    use_llm = st.checkbox("使用 AI 整理（约十几秒；关闭则用零延迟本地解析）",
                          value=True, key="use_llm",
                          help="默认使用 config.toml 中的 google/gemma-4-e4b；超时或失败自动降级，不会卡住。")

# ---------- 对话录入区 ----------
with st.expander("💬 用一句话添加任务 / 问题", expanded=False):
    st.markdown(
        "示例：`添加任务 完成原型评审，负责人 张三，截止 2026-11-20，验收标准 评审通过并留存纪要`\n\n"
        "也可：`问题 接口时间戳格式不一致，关联 T03，状态 待验证，负责人 李四`"
    )
    kind = st.radio("录入类型", ["任务", "问题"], horizontal=True, key="intake_kind_radio")
    user_text = st.text_area("请输入一句话", height=90, key="intake_text",
                             placeholder="例如：新增任务 完成周报整理，负责人 我，下周三截止……")
    if st.button("整理成字段", key="intake_parse"):
        try:
            record, dropped, mode = parse_input(
                user_text, kind, api_key=api_key, base_url=base_url,
                model=model, today=scan_date, use_llm=use_llm,
            )
            st.session_state["intake_draft"] = {
                "kind": kind, "record": record, "dropped": dropped, "mode": mode,
            }
        except Exception as exc:
            st.error(str(exc))

    draft = st.session_state.get("intake_draft")
    if draft:
        kind = draft["kind"]
        record = draft["record"]
        st.caption(f"模式：{draft['mode']}｜以下字段仅供核对，确认后才会加入台账")
        if draft["dropped"]:
            st.warning(
                "已拦截非白名单字段（AI 不得输出判断类内容）：" + "、".join(draft["dropped"])
            )
        fields = TASK_FIELDS if kind == "任务" else ISSUE_FIELDS
        with st.form("intake_confirm_form"):
            edited: dict[str, str] = {}
            cols = st.columns(2)
            for idx, (key, label) in enumerate(fields):
                with cols[idx % 2]:
                    edited[key] = st.text_input(label, value=record.get(key, ""), key=f"draft_{key}")
            if st.form_submit_button("✅ 确认加入台账"):
                target = st.session_state["chat_tasks"] if kind == "任务" else st.session_state["chat_issues"]
                if not edited.get("task_name" if kind == "任务" else "issue_title", "").strip():
                    st.error("名称不能为空。")
                else:
                    edited["source_file"] = "对话录入"
                    target.append(edited)
                    st.session_state["intake_draft"] = None
                    st.success(f"已加入{kind}台账，共 {len(target)} 条；风险将由规则重新计算。")
                    st.rerun()

    # 让 AI/本地解析提示还缺什么（仅录入提示，不是判断）
    if draft:
        missing = missing_fields(draft["record"], draft["kind"])
        if missing:
            st.info("建议补充以下字段，以便规则完整核查：" + "、".join(missing))

    n_task, n_issue = len(st.session_state["chat_tasks"]), len(st.session_state["chat_issues"])
    if n_task or n_issue:
        st.caption(f"本次会话已录入：任务 {n_task} 条、问题 {n_issue} 条（刷新页面后清空）")
        if st.button("清空对话录入记录", key="intake_clear"):
            st.session_state["chat_tasks"] = []
            st.session_state["chat_issues"] = []
            st.session_state["intake_draft"] = None
            st.rerun()

# ---------- 规则说明：定义来自 risk_rules.rule_descriptions()，与执行逻辑同源 ----------
with st.expander("📐 规则说明（判定完全由确定性规则完成，AI 不参与）", expanded=False):
    st.caption(
        f"当前阈值：距截止 ≤ {NEAR_DUE_DAYS} 天算临近截止；≥ {STALE_DAYS} 天未更新算进度异常。"
        "每条风险都会保留触发证据与建议动作；等级只是展示排序，不代表录用概率。")
    show_table(pd.DataFrame(rule_descriptions()))
    st.markdown(
        "**判断权边界**：AI 只把一句话整理成字段；是否逾期、是否算风险、风险等级，"
        "全部由 `risk_rules.py` 的日期减法与字段检查决定。完成状态不等于验证通过，"
        "所以「已完成但无证据」「修复后待验证」仍会被列为风险。")

chat_tasks = st.session_state["chat_tasks"]
chat_issues = st.session_state["chat_issues"]
has_task_upload = bool(task_files)
has_issue_upload = bool(issue_files)
has_chat = bool(chat_tasks) or bool(chat_issues)

if not has_task_upload and not has_issue_upload and not has_chat:
    st.info("当前尚未加载数据。可以：① 在左侧上传任务表；② 用上方「用一句话添加任务 / 问题」录入；③ 下载任务表模板填写后上传。")
    st.stop()

try:
    tasks = read_tables(task_files, TASK_COLUMNS) if has_task_upload else []
    issues = read_tables(issue_files, ISSUE_COLUMNS) if has_issue_upload else []
    tasks.extend(chat_tasks)
    issues.extend(chat_issues)
    if not tasks:
        st.warning(
            f"已录入 {len(issues)} 条问题，但任务台账为空。风险扫描需要至少一个任务作为项目主体；"
            "请上传任务表，或用「用一句话添加任务」录入一条任务。"
        )
        with st.expander("查看已录入的问题"):
            show_table(pd.DataFrame(issues).rename(columns={v: k for k, v in ISSUE_COLUMNS.items()} | {"source_file": "来源文件"}))
        st.stop()
except Exception as exc:
    st.error(f"数据读取失败：{exc}。请使用模板检查字段、日期和文件格式。")
    st.stop()

if has_task_upload or has_issue_upload:
    st.sidebar.success(f"已汇总{len(task_files or [])}个任务表、{len(issue_files or [])}个问题表。")
if has_chat:
    st.sidebar.success(f"已加入{len(chat_tasks)}条对话录入任务。")

# 无论数据来源是上传还是对话录入，都要检查编号冲突。
task_duplicates = duplicate_ids(tasks, "task_id")
issue_duplicates = duplicate_ids(issues, "issue_id")
if task_duplicates:
    st.warning("任务台账存在重复任务编号：" + "、".join(task_duplicates) + "。当前保留全部记录；建议核对后再扫描，以免关联混淆。")
if issue_duplicates:
    st.warning("问题台账存在重复问题编号：" + "、".join(issue_duplicates) + "。当前保留全部记录，请核对是否重复录入。")

risks = scan_project(tasks, issues, scan_date)
summary = project_summary(tasks, issues, risks)
report = generate_report(tasks, issues, risks, scan_date)

c = st.columns(5)
c[0].metric("任务总数", summary["tasks"])
c[1].metric("标记完成", summary["done"])
c[2].metric("未闭环问题", summary["open_issues"])
c[3].metric("严重风险", summary["critical"])
c[4].metric("全部风险", summary["risks"])

tab1, tab2, tab3, tab4 = st.tabs(["风险看板", "任务与验证", "问题闭环", "项目周报"])
with tab1:
    st.subheader("风险清单")
    st.info("风险基于截止日期、状态、最后更新、负责人、验收标准及验证证据等字段触发；每条均保留证据。")
    if risks:
        df = pd.DataFrame(risks).rename(columns={"level": "等级", "category": "类型", "title": "风险", "evidence": "触发证据", "action": "建议动作", "task_id": "任务编号"})
        show_table(df)
        st.download_button("导出风险清单", df.to_csv(index=False).encode("utf-8-sig"), "项目风险清单.csv", "text/csv")
    else:
        st.success("当前规则未识别风险；仍需人工确认数据是否完整。")
with tab2:
    st.subheader("任务台账与验收状态")
    show = pd.DataFrame(tasks).rename(columns={v: k for k, v in TASK_COLUMNS.items()} | {"source_file": "来源文件"})
    show_table(show)
    st.caption("标记“已完成”但缺少验证证据的任务会进入风险清单。")
with tab3:
    st.subheader("问题记录")
    show_table(pd.DataFrame(issues).rename(columns={v: k for k, v in ISSUE_COLUMNS.items()} | {"source_file": "来源文件"}))
with tab4:
    st.subheader("自动生成的项目周报")
    st.code(report, language="markdown")
    st.download_button("下载Markdown周报", report.encode("utf-8"), f"项目周报_{scan_date.isoformat()}.md", "text/markdown")



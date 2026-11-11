"""可解释的项目风险规则；不使用大模型作风险判断。"""
from datetime import date
from typing import Any

DONE_STATUSES = {"已完成", "已关闭", "done", "closed"}
OPEN_ISSUE_STATUSES = {"待处理", "处理中", "待验证", "open", "in_progress"}

# 阈值只在这里定义一次：规则逻辑与界面说明共用，避免"代码改了、说明没改"。
NEAR_DUE_DAYS = 3      # 距截止不超过 N 天 → 临近截止
STALE_DAYS = 7         # 超过 N 天未更新 → 进度异常


def rule_descriptions() -> list[dict[str, str]]:
    """界面「规则说明」的唯一数据源；与 scan_project 的触发条件一一对应。

    返回字段：等级、类别、触发条件、依据字段、建议动作。
    """
    return [
        {"等级": "严重", "类别": "进度延期",
         "触发条件": f"任务未完成，且截止日期早于核查日期",
         "依据字段": "截止日期、状态", "建议动作": "确认阻塞原因并形成恢复计划，不掩盖延期"},
        {"等级": "高", "类别": "临近截止",
         "触发条件": f"任务未完成，且距截止 ≤ {NEAR_DUE_DAYS} 天",
         "依据字段": "截止日期、状态", "建议动作": "确认剩余工作、依赖与验证安排，必要时提前升级"},
        {"等级": "高", "类别": "责任缺失",
         "触发条件": "任务未指定负责人",
         "依据字段": "负责人", "建议动作": "明确唯一负责人及下一次跟进时间"},
        {"等级": "高", "类别": "验收风险",
         "触发条件": "任务标记已完成，但缺少验证证据",
         "依据字段": "状态、验证证据", "建议动作": "补充测试/评审证据后再视为完成"},
        {"等级": "高", "类别": "闭环风险",
         "触发条件": "问题处于未闭环状态，但未指定问题负责人",
         "依据字段": "问题状态、问题负责人", "建议动作": "明确负责人、解决期限与验证人"},
        {"等级": "中", "类别": "验收风险",
         "触发条件": "任务缺少验收标准",
         "依据字段": "验收标准", "建议动作": "补充可观察、可验证的完成标准"},
        {"等级": "中", "类别": "进度异常",
         "触发条件": f"任务未完成，且已 ≥ {STALE_DAYS} 天未更新",
         "依据字段": "最后更新、状态", "建议动作": "核实实际进展与阻塞，更新任务记录"},
        {"等级": "中", "类别": "验证待闭环",
         "触发条件": "问题状态为「待验证」",
         "依据字段": "问题状态", "建议动作": "安排复测并记录结果，未通过则重新打开"},
        {"等级": "中", "类别": "数据完整性",
         "触发条件": "问题关联的任务编号不在任务表中",
         "依据字段": "关联任务编号", "建议动作": "修正关联编号，保证问题可追溯"},
    ]


def parse_date(value: Any) -> date | None:
    if value is None or str(value).strip() in {"", "None", "NaT", "nan"}:
        return None
    text = str(value).strip()[:10].replace("/", "-").replace(".", "-")
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_done(task: dict[str, Any]) -> bool:
    return clean(task.get("status")).lower() in DONE_STATUSES


def risk(level: str, category: str, title: str, evidence: str, action: str, task_id: str = "") -> dict[str, str]:
    return {"level": level, "category": category, "title": title,
            "evidence": evidence, "action": action, "task_id": task_id}


def scan_project(tasks: list[dict[str, Any]], issues: list[dict[str, Any]], today: date | None = None) -> list[dict[str, str]]:
    """每条风险都附带触发证据和建议动作，规则顺序决定展示优先级。"""
    today = today or date.today()
    risks: list[dict[str, str]] = []
    for task in tasks:
        name = clean(task.get("task_name")) or "未命名任务"
        tid = clean(task.get("task_id"))
        due = parse_date(task.get("due_date"))
        status = clean(task.get("status")) or "未填写"
        owner = clean(task.get("owner"))
        updated = parse_date(task.get("last_update"))
        acceptance = clean(task.get("acceptance_criteria"))
        evidence_link = clean(task.get("evidence_link"))
        if not owner:
            risks.append(risk("高", "责任缺失", f"{name}：未指定负责人", "负责人字段为空", "明确唯一负责人及下一次跟进时间。", tid))
        if not acceptance:
            risks.append(risk("中", "验收风险", f"{name}：缺少验收标准", "验收标准字段为空", "补充可观察、可验证的完成标准，再进入交付。", tid))
        if due and not is_done(task):
            days = (due - today).days
            if days < 0:
                risks.append(risk("严重", "进度延期", f"{name}：已逾期{-days}天", f"截止日期{due.isoformat()}；当前状态：{status}", "确认阻塞原因，重新评估节点并形成恢复计划；不要仅修改截止日期掩盖延期。", tid))
            elif days <= NEAR_DUE_DAYS:
                risks.append(risk("高", "临近截止", f"{name}：距离截止{days}天", f"截止日期{due.isoformat()}；当前状态：{status}", "确认剩余工作、依赖和验证安排，必要时提前升级风险。", tid))
        if updated and not is_done(task) and (today - updated).days >= STALE_DAYS:
            risks.append(risk("中", "进度异常", f"{name}：已{(today-updated).days}天未更新", f"最后更新{updated.isoformat()}；当前状态：{status}", "向负责人核实实际进展、阻塞与下一步，更新任务记录。", tid))
        if is_done(task) and not evidence_link:
            risks.append(risk("高", "验收风险", f"{name}：已完成但缺少验证证据", f"状态为{status}，验证证据字段为空", "补充测试记录、验收截图或评审结论；确认后再视为完成。", tid))
    task_ids = {clean(t.get("task_id")) for t in tasks}
    for issue in issues:
        name = clean(issue.get("issue_title")) or "未命名问题"
        tid = clean(issue.get("task_id"))
        status = clean(issue.get("issue_status")) or "待处理"
        owner = clean(issue.get("issue_owner"))
        if status.lower() in OPEN_ISSUE_STATUSES and not owner:
            risks.append(risk("高", "闭环风险", f"{name}：未指定问题负责人", f"问题状态：{status}；负责人为空", "明确问题负责人、解决期限及验证人，避免问题无人跟进。", tid))
        if status == "待验证":
            risks.append(risk("中", "验证待闭环", f"{name}：修复后尚待验证", "问题状态为待验证", "安排复测并记录结果；未通过时重新打开问题。", tid))
        if tid and tid not in task_ids:
            risks.append(risk("中", "数据完整性", f"{name}：关联任务不存在", f"问题关联任务编号{tid}不在任务表中", "修正关联任务编号，保证问题可追溯到具体交付项。", tid))
    priority = {"严重": 0, "高": 1, "中": 2}
    return sorted(risks, key=lambda x: priority.get(x["level"], 9))


def project_summary(tasks: list[dict[str, Any]], issues: list[dict[str, Any]], risks: list[dict[str, str]]) -> dict[str, int]:
    return {"tasks": len(tasks), "done": sum(is_done(t) for t in tasks),
            "open_issues": sum(clean(i.get("issue_status")).lower() in OPEN_ISSUE_STATUSES for i in issues),
            "critical": sum(r["level"] == "严重" for r in risks),
            "high": sum(r["level"] == "高" for r in risks),
            "risks": len(risks)}

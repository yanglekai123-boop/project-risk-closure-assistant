"""基于结构化任务与规则结果生成可复核的Markdown周报，不调用大模型。"""
from datetime import date
from risk_rules import clean, is_done, project_summary


def generate_report(tasks: list[dict], issues: list[dict], risks: list[dict], today: date | None = None) -> str:
    today = today or date.today()
    s = project_summary(tasks, issues, risks)
    done = [clean(t.get("task_name")) for t in tasks if is_done(t)]
    completed = [clean(t.get("completed_this_week")) for t in tasks if clean(t.get("completed_this_week"))]
    next_steps = [f"{clean(t.get('task_name'))}：{clean(t.get('next_step'))}" for t in tasks if clean(t.get("next_step"))]
    lines = [f"# 项目周报｜{today.isoformat()}", "",
             "> 本报告由结构化任务及明确规则自动生成；风险建议需项目负责人确认，不代表AI自动作出管理决策。", "",
             "## 一、项目概况", "",
             f"- 任务总数：{s['tasks']}；标记已完成：{s['done']}；未闭环问题：{s['open_issues']}。",
             f"- 风险共{s['risks']}项，其中严重{s['critical']}项、高{s['high']}项。", "",
             "## 二、本周完成", ""]
    lines += [f"- {x}" for x in (completed or done)] or ["- 暂未填写本周完成事项。"]
    lines += ["", "## 三、重点风险与建议", ""]
    lines += [f"- **{r['level']}｜{r['category']}**：{r['title']}。证据：{r['evidence']}。建议：{r['action']}" for r in risks] or ["- 当前规则未识别风险；仍需人工确认任务记录是否完整。"]
    lines += ["", "## 四、下周计划", ""]
    lines += [f"- {x}" for x in next_steps] or ["- 请项目负责人补充下周计划。"]
    return "\n".join(lines) + "\n"

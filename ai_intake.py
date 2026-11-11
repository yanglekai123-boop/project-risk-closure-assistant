"""对话式录入：AI 只负责把一句话整理成结构化字段，不参与任何风险判断。

设计边界（重要）：
- 允许：非结构化文本 -> 任务表/问题表白名单字段
- 禁止：风险等级、优先级、是否紧急、延期结论等一切判断性字段
- 白名单在 sanitize() 中硬编码执行，即使模型返回越权字段也会被丢弃
- 是否加入台账由用户点击确认决定；判断仍由 risk_rules.py 的确定性规则完成
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def load_config() -> dict[str, object]:
    """读取与 app.py 同目录的 config.toml；文件缺失时返回内置默认值。"""
    default: dict[str, object] = {
        "base_url": "https://api.openai.com/v1", "model": "", "timeout_seconds": 180,
    }
    path = Path(__file__).with_name("config.toml")
    if tomllib is None or not path.exists():
        return default
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    try:
        timeout = int(data.get("timeout_seconds") or 180)
    except (TypeError, ValueError):
        timeout = 180
    return {
        "base_url": str(data.get("base_url") or default["base_url"]),
        "model": str(data.get("model") or ""),
        "timeout_seconds": max(10, timeout),
    }


def list_models(base_url: str, api_key: str = "", timeout: int = 8) -> list[str]:
    """调用 /models 检查本地服务是否可用，返回模型 id 列表。"""
    url = base_url.rstrip("/") + "/models"
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    req = urlrequest.Request(url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return [str(item.get("id")) for item in body.get("data", []) if item.get("id")]
    except Exception as exc:
        raise RuntimeError(f"连接失败：{exc}。请确认本地服务已启动、地址含 /v1。") from exc

# 白名单：只允许这些字段进入台账。任何"判断类"字段都不在此列。
TASK_FIELDS = [
    ("task_id", "任务编号"), ("task_name", "任务名称"), ("owner", "负责人"),
    ("due_date", "截止日期"), ("status", "状态"), ("last_update", "最后更新"),
    ("acceptance_criteria", "验收标准"), ("evidence_link", "验证证据"),
    ("completed_this_week", "本周完成"), ("next_step", "下周计划"),
]
ISSUE_FIELDS = [
    ("issue_id", "问题编号"), ("task_id", "关联任务编号"), ("issue_title", "问题描述"),
    ("issue_status", "问题状态"), ("issue_owner", "问题负责人"),
    ("verification_result", "验证结果"),
]

ALLOWED_KEYS = {
    "任务": {k for k, _ in TASK_FIELDS},
    "问题": {k for k, _ in ISSUE_FIELDS},
}

# 录入时建议补齐的关键字段（仅用于提示用户，不影响规则执行）
RECOMMENDED = {
    "任务": ["task_name", "owner", "due_date", "acceptance_criteria", "status"],
    "问题": ["issue_title", "task_id", "issue_status", "issue_owner"],
}
RECOMMENDED_LABELS = {k: v for k, v in TASK_FIELDS + ISSUE_FIELDS}

SYSTEM_PROMPT = """把用户的一句话整理成 JSON。只抽取信息，不做判断、不评价、不建议。
禁止输出风险等级、优先级、是否紧急、是否延期等判断字段。
没提到的字段留空字符串，不要编造。日期写成 YYYY-MM-DD，相对日期按给定今天换算。
只输出一个 JSON 对象，不要解释、不要代码块。
任务字段：task_id, task_name, owner, due_date, status, last_update, acceptance_criteria, evidence_link, completed_this_week, next_step
问题字段：issue_id, task_id, issue_title, issue_status, issue_owner, verification_result
"""


def sanitize(record: Any, kind: str) -> tuple[dict[str, str], list[str]]:
    """硬约束：仅保留白名单字段，返回(干净记录, 被丢弃的越权字段)。"""
    allowed = ALLOWED_KEYS.get(kind, set())
    if not isinstance(record, dict):
        return {}, ["<非对象输出>"]
    clean: dict[str, str] = {}
    dropped: list[str] = []
    for key, value in record.items():
        if key not in allowed:
            dropped.append(str(key))
            continue
        if value is None:
            text = ""
        else:
            text = str(value).strip()
        if text.lower() in {"none", "nan", "nat", "null"}:
            text = ""
        clean[str(key)] = text
    return clean, dropped


def missing_fields(record: dict[str, str], kind: str) -> list[str]:
    """提示用户还缺哪些关键字段。这是"录入提示"，不是风险判断。"""
    return [RECOMMENDED_LABELS[k] for k in RECOMMENDED.get(kind, [])
            if not record.get(k, "").strip()]


def _extract_json(text: str) -> dict:
    """兼容模型返回裸 JSON 或 Markdown 代码块。"""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if match:
        text = match.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def parse_local(text: str, kind: str, today: date | None = None) -> dict[str, str]:
    """无 API Key 时的降级解析：关键词/正则抽取，行为与 AI 模式完全一致。"""
    today = today or date.today()
    record: dict[str, str] = {}

    def grab(patterns: list[str]) -> str:
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip(" ，,；;。:：")
        return ""

    if kind == "任务":
        record["task_name"] = grab([r"(?:添加|新增|记录)?任务[：:\s]*(.+?)(?=[，,；;。]|$)",
                                    r"^(.+?)(?=[，,；;。]|$)"])
        record["owner"] = grab([r"负责人[是：:\s]*([^\s，,；;。]+)"])
        record["due_date"] = grab([r"(?:截止|截止日期|deadline|到期)[是：:\s]*(\d{4}-\d{1,2}-\d{1,2})"])
        record["status"] = grab([r"状态[是：:\s]*([^\s，,；;。]+)"]) or "进行中"
        record["acceptance_criteria"] = grab([r"验收标准[是：:\s]*(.+?)(?=[，,；;。]|$)",
                                              r"完成标准[是：:\s]*(.+?)(?=[，,；;。]|$)"])
        record["next_step"] = grab([r"(?:下周计划|下一步)[是：:\s]*(.+?)(?=[，,；;。]|$)"])
        record["last_update"] = today.isoformat()
        record["task_id"] = ""
        record["evidence_link"] = ""
        record["completed_this_week"] = ""
    else:
        record["issue_title"] = grab([r"(?:添加|新增|记录)?问题[：:\s]*(.+?)(?=[，,；;。]|$)",
                                      r"^(.+?)(?=[，,；;。]|$)"])
        record["task_id"] = grab([r"(?:关联|属于|对应)(?:任务)?(?:编号)?[是：:\s]*([A-Za-z0-9_-]+)"])
        record["issue_status"] = grab([r"状态[是：:\s]*([^\s，,；;。]+)"]) or "待处理"
        record["issue_owner"] = grab([r"负责人[是：:\s]*([^\s，,；;。]+)"])
        record["issue_id"] = ""
        record["verification_result"] = ""

    # 相对日期的轻量换算（AI 模式由模型换算，这里做最小兜底）
    if not record.get("due_date"):
        if "今天" in text:
            record["due_date"] = today.isoformat()
        elif "明天" in text:
            record["due_date"] = (today + timedelta(days=1)).isoformat()
        elif "下周" in text:
            record["due_date"] = (today + timedelta(days=7)).isoformat()
    return sanitize(record, kind)[0]


def parse_with_llm(text: str, kind: str, api_key: str, base_url: str,
                   model: str, today: date | None = None,
                   timeout: int = 180) -> tuple[dict[str, str], list[str]]:
    """调用 OpenAI 兼容接口；返回(干净记录, 被丢弃的越权字段)。失败时抛出中文异常。"""
    today = today or date.today()
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"今天是 {today.isoformat()}。条目类型 kind={kind}。\n"
                f"请把下面这句话整理成字段，只输出 JSON：\n{text}"
            )},
        ],
    }
    headers = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        # 本地服务一般不校验 key；若填了则按标准 Bearer 传，兼容云端接口。
        headers["Authorization"] = f"Bearer {key}"
    req = urlrequest.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = body["choices"][0]["message"]
        content = (message.get("content") or "").strip()
        # 推理型模型常把结论写在 reasoning_content、content 为空；
        # 尝试从思考文本末尾提取最后一个 JSON 对象作为兜底。
        if not content:
            reasoning = (message.get("reasoning_content") or "").strip()
            if reasoning:
                end = reasoning.rfind("}")
                start = reasoning.rfind("{", 0, end + 1) if end >= 0 else -1
                if start >= 0:
                    content = reasoning[start:end + 1]
        if not content:
            raise RuntimeError("模型未返回可用文本")
        return sanitize(_extract_json(content), kind)
    except KeyError as exc:
        raise RuntimeError("模型返回格式异常，未找到文本内容；可点击「使用本地解析」切换。") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型未返回合法 JSON；可点击「使用本地解析」切换，或换一个模型。") from exc
    except Exception as exc:
        raise RuntimeError(f"调用模型失败：{exc}。可点击「使用本地解析」切换，功能仍可用。") from exc


def parse_input(text: str, kind: str, api_key: str = "", base_url: str = "",
                model: str = "", today: date | None = None,
                use_llm: bool = True,
                timeout: int | None = None) -> tuple[dict[str, str], list[str], str]:
    """统一入口，返回(记录, 被丢弃字段, 使用的模式说明)。

    use_llm=False 时强制走本地解析（用户主动选择或本地服务不可用时）。
    本地 OpenAI 兼容服务通常不需要 API Key：只要填了非云端地址即尝试调用。
    """
    today = today or date.today()
    if not text.strip():
        return {}, [], ""
    if not use_llm:
        return parse_local(text, kind, today), [], "本地解析（用户选择）"
    cfg = load_config()
    url = (base_url or "").strip() or cfg["base_url"]
    chosen_model = (model or "").strip() or cfg["model"] or "default"
    is_local = url.startswith("http://localhost") or url.startswith("http://127.0.0.1")
    key = (api_key or "").strip()
    if is_local or key:
        try:
            record, dropped = parse_with_llm(
                text, kind, key, url, chosen_model, today,
                timeout=timeout or int(cfg["timeout_seconds"]),
            )
            # 模型可能只返回空对象；视为失败，降级而不是交出空白草稿。
            if not record:
                raise RuntimeError("模型未返回可用字段")
            return record, dropped, f"AI整理（{url}，仅抽取字段）"
        except Exception:
            # 本地大模型可能加载慢/超时/返回异常；自动降级，不阻塞录入。
            return parse_local(text, kind, today), [], "本地解析（AI服务不可用或超时，已自动降级）"
    return parse_local(text, kind, today), [], "本地解析（未配置API Key且非本地服务）"

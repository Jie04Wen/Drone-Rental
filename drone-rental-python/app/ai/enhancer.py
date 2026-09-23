"""Rule-based conversation enhancements from ConversationEnhancer.java."""

from __future__ import annotations

from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AiChatTrace


INTENT_KEYWORDS: dict[str, list[str]] = OrderedDict(
    [
        ("device_query", ["无人机", "设备", "型号", "品牌", "推荐", "租赁", "库存"]),
        ("order_query", ["订单", "支付", "发货", "收货", "归还", "取消", "退款"]),
        ("qualification", ["资质", "认证", "执照", "飞行证", "审核"]),
        ("fault_report", ["故障", "损坏", "坏了", "报修", "维修"]),
        ("airspace", ["空域", "备案", "飞行区域", "禁飞"]),
        ("pricing", ["价格", "费用", "多少钱", "租金", "押金"]),
        ("process", ["流程", "怎么", "如何", "步骤", "操作"]),
    ]
)


SUGGESTIONS = {
    "device_query": ["这些设备的详细参数对比", "哪款最适合航拍新手", "租赁流程是怎样的"],
    "order_query": ["如何取消订单", "退款需要多长时间", "订单状态是什么意思"],
    "qualification": ["需要什么资质才能飞行", "资质审核需要多久", "如何提交资质认证"],
    "fault_report": ["报修后多久能修好", "设备损坏怎么赔偿", "紧急情况怎么处理"],
    "airspace": ["哪些地方不能飞", "备案需要多长时间", "飞行高度有什么限制"],
    "pricing": ["押金是多少", "逾期怎么收费", "有没有优惠套餐"],
    "process": ["具体操作步骤", "需要准备什么材料", "有什么注意事项"],
    "general": ["推荐一台适合的无人机", "租赁流程是怎样的", "常见问题有哪些"],
}


def detect_intent(message: str) -> str:
    lower = message.lower()
    scores = {
        intent: sum(1 for keyword in keywords if keyword in lower)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    scores = {intent: score for intent, score in scores.items() if score > 0}
    return max(scores, key=scores.get) if scores else "general"


def follow_up_suggestions(intent: str) -> list[str]:
    return list(SUGGESTIONS.get(intent, SUGGESTIONS["general"]))[:3]


def summarize_context(db: Session, session_id: str, user_id: int, max_messages: int = 20) -> str | None:
    messages = list(
        db.scalars(
            select(AiChatTrace)
            .where(AiChatTrace.session_id == session_id, AiChatTrace.user_id == user_id)
            .order_by(AiChatTrace.created_time.desc())
            .limit(max_messages)
        ).all()
    )
    if len(messages) <= 5:
        return None

    topics: set[str] = set()
    entities: set[str] = set()
    for message in messages:
        if message.role != "user":
            continue
        content = message.content.lower()
        if "mavic" in content:
            entities.add("DJI Mavic 系列")
        if "mini" in content:
            entities.add("DJI Mini 系列")
        if "air" in content:
            entities.add("DJI Air 系列")
        if "租赁" in content or "租" in content:
            topics.add("租赁咨询")
        if "故障" in content or "损坏" in content:
            topics.add("故障报修")
        if "资质" in content or "认证" in content:
            topics.add("资质认证")
        if "价格" in content or "费用" in content:
            topics.add("费用咨询")

    summary = "【对话摘要】用户之前咨询了以下内容："
    if topics:
        summary += "主题包括" + "、".join(sorted(topics))
    if entities:
        summary += "，涉及设备：" + "、".join(sorted(entities))
    return summary + "。请基于上下文继续回答用户问题。"


def is_topic_switch(previous_message: str | None, current_message: str) -> bool:
    if previous_message is None:
        return False
    previous = detect_intent(previous_message)
    current = detect_intent(current_message)
    return previous != current and previous != "general" and current != "general"

"""OpenAI-compatible chat, tool calling, traces, and SSE streaming."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common import BusinessException, ResultCode
from ..config import Settings
from ..models import AiChatTrace, AiImageAttachment, AiMemory, AiToolCallLog, Drone
from ..schemas import AiChatDTO
from ..storage import get_storage
from .enhancer import detect_intent, follow_up_suggestions, summarize_context
from .mcp import McpToolClient
from .ragflow import RagflowClient
from .tools import TOOL_REGISTRY, resolve_drone_by_model, tool_definitions
from .vision import prepare_image, to_data_url

LOGGER = logging.getLogger(__name__)

PRICE_KEYWORDS = ("价格", "费用", "多少钱", "租金", "押金", "总计", "合计", "总共", "总费用")
DRONE_LIST_PATTERNS = (
    "当前有哪些可以租赁", "当前有哪些可租赁", "有哪些可以租赁的无人机",
    "有哪些可租赁的无人机", "当前有什么可以租赁", "当前可租赁的无人机",
)
DRONE_AVAILABILITY_KEYWORDS = (
    "有吗", "有嘛", "有货", "有现货", "可以租", "可租", "能租", "可租赁情况", "是否", "吗", "么"
)
CHINESE_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9}


class AiChatService:
    """对应 Java：AiChatServiceImpl.java。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.ragflow = RagflowClient(settings)
        self.mcp = McpToolClient(settings) if settings.ai_mcp_server_enabled else None

    def ensure_enabled(self) -> None:
        if not self.settings.ai_model_enabled or not self.settings.ai_model_api_key:
            raise BusinessException(ResultCode.SERVICE_UNAVAILABLE, "AI服务未启用或未配置API密钥")

    def chat(self, db: Session, dto: AiChatDTO, user_id: int) -> dict[str, Any]:
        self.ensure_enabled()
        session_id = dto.session_id or uuid4().hex
        self._save_trace(db, session_id, user_id, "user", dto.message)
        intent = detect_intent(dto.message)
        direct_price = None
        if self.mcp is None:
            direct_price = self._try_direct_price_calculation(
                db, session_id, user_id, dto.message
            )
        if direct_price is not None:
            self._save_trace(
                db, session_id, user_id, "assistant", direct_price,
                model="deterministic-price-calculator",
            )
            db.commit()
            return {
                "sessionId": session_id,
                "role": "assistant",
                "content": direct_price,
                "model": "deterministic-price-calculator",
                "createdTime": datetime.now(),
                "suggestions": follow_up_suggestions(intent),
                "intent": intent,
            }
        direct_drone = None
        if self.mcp is None:
            direct_drone = self._try_direct_drone_query(
                db, session_id, user_id, dto.message
            )
        if direct_drone is not None:
            self._save_trace(
                db, session_id, user_id, "assistant", direct_drone,
                model="deterministic-drone-query",
            )
            db.commit()
            return {
                "sessionId": session_id,
                "role": "assistant",
                "content": direct_drone,
                "model": "deterministic-drone-query",
                "createdTime": datetime.now(),
                "suggestions": follow_up_suggestions(intent),
                "intent": intent,
            }
        summary = summarize_context(db, session_id, user_id, 20)
        enriched = self._enrich_with_rag(dto.message)
        messages = self._build_messages(db, session_id, user_id, enriched, summary)
        request = {
            "model": self.settings.ai_model_chat_model,
            "messages": messages,
            "max_tokens": self.settings.ai_max_tokens,
            "temperature": self.settings.ai_temperature,
            "tools": self._tool_definitions(),
        }

        started = time.perf_counter()
        response = self._call_api(request)
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = (((response.get("choices") or [{}])[0].get("message")) or {})
        content = message.get("content") or ""
        calls = message.get("tool_calls") or []
        if calls:
            tool_messages = self._execute_tool_calls(db, calls, session_id, user_id)
            follow_up_messages = list(messages)
            follow_up_messages.append(
                {"role": "assistant", "content": content, "tool_calls": calls}
            )
            follow_up_messages.extend(tool_messages)
            follow_up = self._call_api(
                {
                    "model": self.settings.ai_model_chat_model,
                    "messages": follow_up_messages,
                    "max_tokens": self.settings.ai_max_tokens,
                    "temperature": self.settings.ai_temperature,
                }
            )
            final_message = (((follow_up.get("choices") or [{}])[0].get("message")) or {})
            content = final_message.get("content") or "\n".join(
                item["content"] for item in tool_messages
            )

        self._save_trace(
            db,
            session_id,
            user_id,
            "assistant",
            content,
            model=self.settings.ai_model_chat_model,
            latency_ms=latency_ms,
        )
        db.commit()
        return {
            "sessionId": session_id,
            "role": "assistant",
            "content": content,
            "model": self.settings.ai_model_chat_model,
            "createdTime": datetime.now(),
            "suggestions": follow_up_suggestions(intent),
            "intent": intent,
        }

    def stream_chat(self, db: Session, dto: AiChatDTO, user_id: int) -> Generator[str, None, None]:
        self.ensure_enabled()
        session_id = dto.session_id or uuid4().hex
        self._save_trace(db, session_id, user_id, "user", dto.message)
        direct_price = None
        if self.mcp is None:
            direct_price = self._try_direct_price_calculation(
                db, session_id, user_id, dto.message
            )
        if direct_price is not None:
            self._save_trace(
                db, session_id, user_id, "assistant", direct_price,
                model="deterministic-price-calculator",
            )
            db.commit()
            yield direct_price
            yield "[DONE]"
            return
        direct_drone = None
        if self.mcp is None:
            direct_drone = self._try_direct_drone_query(
                db, session_id, user_id, dto.message
            )
        if direct_drone is not None:
            self._save_trace(
                db, session_id, user_id, "assistant", direct_drone,
                model="deterministic-drone-query",
            )
            db.commit()
            yield direct_drone
            yield "[DONE]"
            return
        summary = summarize_context(db, session_id, user_id, 20)
        messages = self._build_messages(
            db, session_id, user_id, self._enrich_with_rag(dto.message), summary
        )
        first_request = {
            "model": self.settings.ai_model_chat_model,
            "messages": messages,
            "max_tokens": self.settings.ai_max_tokens,
            "temperature": self.settings.ai_temperature,
            "stream": True,
            "tools": self._tool_definitions(),
        }
        full_content: list[str] = []
        tool_calls = yield from self._stream_round(first_request, full_content)

        if tool_calls:
            tool_messages = self._execute_tool_calls(db, tool_calls, session_id, user_id)
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(full_content),
                    "tool_calls": tool_calls,
                }
            )
            messages.extend(tool_messages)
            second_content: list[str] = []
            yield from self._stream_round(
                {
                    "model": self.settings.ai_model_chat_model,
                    "messages": messages,
                    "max_tokens": self.settings.ai_max_tokens,
                    "temperature": self.settings.ai_temperature,
                    "stream": True,
                },
                second_content,
            )
            full_content.extend(second_content)

        self._save_trace(
            db,
            session_id,
            user_id,
            "assistant",
            "".join(full_content),
            model=self.settings.ai_model_chat_model,
        )
        db.commit()
        yield "[DONE]"

    def history(self, db: Session, session_id: str, user_id: int) -> list[dict[str, Any]]:
        items = list(db.scalars(
            select(AiChatTrace)
            .where(
                AiChatTrace.session_id == session_id,
                AiChatTrace.user_id == user_id,
                AiChatTrace.role.in_(["user", "assistant"]),
            )
            .order_by(AiChatTrace.created_time.asc())
        ).all())
        if not items:
            return []

        attachments = list(db.scalars(
            select(AiImageAttachment)
            .where(
                AiImageAttachment.session_id == session_id,
                AiImageAttachment.user_id == user_id,
                AiImageAttachment.trace_id.in_([item.id for item in items]),
            )
            .order_by(AiImageAttachment.created_time.asc())
        ).all())
        attachments_by_trace: dict[int, list[AiImageAttachment]] = {}
        for attachment in attachments:
            if attachment.trace_id is not None:
                attachments_by_trace.setdefault(attachment.trace_id, []).append(attachment)

        now = datetime.now()
        has_active_attachment = any(
            attachment.deleted == 0 and attachment.expires_at > now
            for attachment in attachments
        )
        storage = get_storage(self.settings) if has_active_attachment else None
        result: list[dict[str, Any]] = []

        for item in items:
            item_attachments = attachments_by_trace.get(item.id, [])
            content = item.content
            if item_attachments and content.startswith("[图片识别] "):
                content = content.removeprefix("[图片识别] ")

            history_item: dict[str, Any] = {
                "sessionId": item.session_id,
                "role": item.role,
                "content": content,
                "model": item.model,
                "createdTime": item.created_time,
            }

            if item_attachments:
                attachment_payloads = []
                for attachment in item_attachments:
                    expired = attachment.deleted != 0 or attachment.expires_at <= now
                    url = None
                    if not expired and storage is not None:
                        try:
                            url = storage.get_access_url(attachment.object_key)
                        except Exception:
                            LOGGER.warning(
                                "AI历史图片访问地址生成失败：%s",
                                attachment.object_key,
                                exc_info=True,
                            )

                    attachment_payloads.append(
                        {
                            "id": attachment.id,
                            "type": "image",
                            "url": url,
                            "expiresAt": attachment.expires_at,
                            "expired": expired,
                            "available": bool(url) and not expired,
                            "originalName": attachment.original_name,
                            "mimeType": attachment.mime_type,
                            "sizeBytes": attachment.size_bytes,
                        }
                    )

                history_item["attachments"] = attachment_payloads

            result.append(history_item)

        return result

    def _call_api(self, request: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=httpx.Timeout(60, connect=5)) as client:
            response = client.post(
                self.settings.ai_chat_completions_url,
                headers={"Authorization": "Bearer " + self.settings.ai_model_api_key},
                json=request,
            )
            self._raise_for_status(response)
            return response.json()

    def _stream_round(
            self, request: dict[str, Any], full_content: list[str]
    ) -> Generator[str, None, list[dict[str, Any]] | None]:
        accumulated: dict[int, dict[str, Any]] = {}
        with httpx.Client(timeout=httpx.Timeout(60, connect=5)) as client:
            with client.stream(
                    "POST",
                    self.settings.ai_chat_completions_url,
                    headers={"Authorization": "Bearer " + self.settings.ai_model_api_key},
                    json=request,
            ) as response:
                self._raise_for_status(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    node = json.loads(data)
                    delta = ((((node.get("choices") or [{}])[0]).get("delta")) or {})
                    chunk = delta.get("content")
                    if chunk:
                        full_content.append(chunk)
                        yield chunk
                    for call in delta.get("tool_calls") or []:
                        index = int(call.get("index", 0))
                        entry = accumulated.setdefault(
                            index,
                            {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
                        )
                        if call.get("id"):
                            entry["id"] = call["id"]
                        function = call.get("function") or {}
                        if function.get("name"):
                            entry["function"]["name"] = function["name"]
                        if function.get("arguments"):
                            entry["function"]["arguments"] += function["arguments"]
        return list(accumulated.values()) or None

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text[:2000]
            LOGGER.error(
                "AI upstream request failed: status=%s body=%s",
                response.status_code,
                detail,
            )
            raise BusinessException(
                ResultCode.SERVICE_UNAVAILABLE,
                f"AI模型服务请求失败（HTTP {response.status_code}）：{detail}",
            ) from exc

    # 增强后的当前用户问题 替换 消息历史中的原始问题 并传给大模型
    def _build_messages(
            self,
            db: Session,
            session_id: str,
            user_id: int,
            user_message: str,
            summary: str | None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt(db, user_id)}
        ]
        if summary:
            messages.append({"role": "system", "content": summary})
        history = list(
            db.scalars(
                select(AiChatTrace)
                .where(AiChatTrace.session_id == session_id, AiChatTrace.user_id == user_id)
                .order_by(AiChatTrace.created_time.desc())
                .limit(10)
            ).all()
        )
        history.reverse()
        for index, item in enumerate(history):
            content = user_message if index == len(history) - 1 and item.role == "user" else item.content
            messages.append({"role": item.role, "content": content})
        if not history or history[-1].role != "user":
            messages.append({"role": "user", "content": user_message})
        return messages

    def _build_system_prompt(self, db: Session, user_id: int) -> str:
        prompt = self.settings.ai_system_prompt + (
            "\n\n## 工具调用硬性规则\n"
            "- 只能调用本次请求 tools 中提供的函数名，禁止编造 query_deposit、"
            "query_order_price 等不存在的工具。\n"
            "- 计算租赁费用、押金或含押金总计时，只能调用 calculate_rental_price。\n"
            "- 用户提供产品型号时传 droneModel，只有用户明确提供数据库ID时才传 droneId。\n"
            "- query_drones 的 totalAvailable 是符合条件的总数，items 只是最多5款的展示列表；"
            "回答时必须区分总数与展示数，不得把 displayedCount 当作总数。\n"
            "- 严禁在回答正文输出 DSML、XML、tool_calls 或 invoke 标签。\n"
            "- 工具返回的金额是数据库真实值，必须原样使用，禁止自行猜测或重新计算。"
        )
        memories = db.scalars(
            select(AiMemory)
            .where(AiMemory.user_id == user_id)
            .order_by(AiMemory.importance.desc())
            .limit(10)
        ).all()
        if memories:
            prompt += "\n\n## 用户记忆\n"
            prompt += "".join(f"- {item.memory_key}: {item.memory_value}\n" for item in memories)
        return prompt

    def _enrich_with_rag(self, message: str) -> str:
        if not self.ragflow.available:
            return message
        context = self.ragflow.retrieve_context(message, 3)
        return f"{context}\n用户问题: {message}" if context else message

    def _try_direct_drone_query(
            self,
            db: Session,
            session_id: str,
            user_id: int,
            message: str,
    ) -> str | None:
        """Answer common list and model-availability questions from live DB data."""
        matched_drone, _ = resolve_drone_by_model(db, message)
        asks_specific = matched_drone is not None and any(
            keyword in message for keyword in DRONE_AVAILABILITY_KEYWORDS
        )
        asks_list = any(pattern in message for pattern in DRONE_LIST_PATTERNS)
        if not asks_specific and not asks_list:
            return None

        params = {"keyword": matched_drone.model.strip()} if asks_specific else {}
        call = {
            "id": "call_drone_" + uuid4().hex,
            "type": "function",
            "function": {
                "name": "query_drones",
                "arguments": json.dumps(params, ensure_ascii=False),
            },
        }
        tool_message = self._execute_tool_calls(
            db, [call], session_id, user_id
        )[0]["content"]
        if asks_specific:
            return self._format_specific_drone(matched_drone)
        return self._format_drone_list(tool_message)

    @staticmethod
    def _format_specific_drone(drone: Drone) -> str:
        model = (drone.model or "").strip()
        available = (
                drone.deleted == 0
                and drone.on_shelf == 1
                and drone.status == 1
                and drone.stock > 0
        )
        if available:
            conclusion = f"**{model} 当前可以租赁。**"
        elif drone.on_shelf != 1:
            conclusion = f"**{model} 当前已下架，暂不可租赁。**"
        elif drone.status != 1:
            conclusion = f"**{model} 当前设备状态异常，暂不可租赁。**"
        else:
            conclusion = f"**{model} 当前库存不足，暂不可租赁。**"
        return (
            "### 无人机可租赁情况\n\n"
            f"{conclusion}\n\n"
            "| 项目 | 信息 |\n|---|---|\n"
            f"| 型号 | {model} |\n"
            f"| 品牌 | {(drone.brand or '-').strip()} |\n"
            f"| 类型 | {(drone.type or '-').strip()} |\n"
            f"| 日租金 | {drone.price_per_day:.2f} 元/天 |\n"
            f"| 库存 | {drone.stock} 台 |\n"
            f"| 上架状态 | {'已上架' if drone.on_shelf == 1 else '已下架'} |\n"
            f"| 设备状态 | {'正常' if drone.status == 1 else '异常'} |"
        )

    @staticmethod
    def _format_drone_list(raw_result: str) -> str:
        try:
            data = json.loads(raw_result)
        except json.JSONDecodeError:
            return "无法解析无人机查询结果，请稍后重试。"
        if data.get("error"):
            return f"无人机查询失败：{data['error']}。"

        items = data.get("items") or []
        total = int(data.get("totalAvailable") or 0)
        displayed = len(items)
        if total == 0:
            return "当前没有已上架且设备状态正常的无人机。"
        if total > displayed:
            summary = (
                f"当前已上架、状态正常的无人机共有 **{total} 款**，"
                f"当前仅展示 **{displayed} 款**无人机机型："
            )
        else:
            summary = (
                f"当前已上架、状态正常的无人机共有 **{total} 款**，以下全部展示："
            )
        rows = "".join(
            f"| {item.get('model')} | {item.get('brand') or '-'} | "
            f"{item.get('type') or '-'} | {item.get('pricePerDay')} 元/天 | "
            f"{item.get('stock')} 台 |\n"
            for item in items
        )
        return (
            f"{summary}\n\n"
            "| 型号 | 品牌 | 类型 | 日租金 | 库存 |\n"
            "|---|---|---|---:|---:|\n"
            f"{rows}"
        )

    def _try_direct_price_calculation(
            self,
            db: Session,
            session_id: str,
            user_id: int,
            message: str,
    ) -> str | None:
        """Handle price calculations deterministically instead of relying on LLM tool choice."""
        if not any(keyword in message for keyword in PRICE_KEYWORDS):
            return None

        days = self._extract_rental_days(message)
        if days is None:
            previous = db.scalar(
                select(AiToolCallLog)
                .where(
                    AiToolCallLog.session_id == session_id,
                    AiToolCallLog.user_id == user_id,
                    AiToolCallLog.tool_name == "calculate_rental_price",
                    AiToolCallLog.status == 1,
                )
                .order_by(AiToolCallLog.id.desc())
                .limit(1)
            )
            if previous and previous.tool_output:
                return self._format_price_result(previous.tool_output)
            return None

        params: dict[str, Any] = {"rentalDays": days}
        drone_id = self._extract_drone_id(message)
        if drone_id is not None:
            params["droneId"] = drone_id
        else:
            model_context = message
            matched_drone, _ = resolve_drone_by_model(db, model_context)
            if matched_drone is None:
                recent_messages = db.scalars(
                    select(AiChatTrace)
                    .where(
                        AiChatTrace.session_id == session_id,
                        AiChatTrace.user_id == user_id,
                    )
                    .order_by(AiChatTrace.id.desc())
                    .limit(8)
                ).all()
                for trace in recent_messages:
                    matched_drone, _ = resolve_drone_by_model(db, trace.content)
                    if matched_drone is not None:
                        model_context = matched_drone.model
                        break
            params["droneModel"] = model_context
        call = {
            "id": "call_price_" + uuid4().hex,
            "type": "function",
            "function": {
                "name": "calculate_rental_price",
                "arguments": json.dumps(params, ensure_ascii=False),
            },
        }
        tool_messages = self._execute_tool_calls(db, [call], session_id, user_id)
        return self._format_price_result(tool_messages[0]["content"])

    @staticmethod
    def _extract_drone_id(message: str) -> int | None:
        matched = re.search(
            r"(?:无人机|设备)?\s*(?:id|ID|编号)\s*(?:为|是|[:：=])?\s*(\d+)",
            message,
        )
        return int(matched.group(1)) if matched else None

    @staticmethod
    def _extract_rental_days(message: str) -> int | None:
        matched = re.search(r"(\d+)\s*(?:天|日)", message)
        if matched:
            return int(matched.group(1))
        matched = re.search(r"([一二两三四五六七八九十]+)\s*(?:天|日)", message)
        if not matched:
            return None
        value = matched.group(1)
        if value == "十":
            return 10
        if "十" in value:
            left, right = value.split("十", 1)
            return CHINESE_DIGITS.get(left, 1) * 10 + CHINESE_DIGITS.get(right, 0)
        return CHINESE_DIGITS.get(value)

    @staticmethod
    def _format_price_result(raw_result: str) -> str:
        try:
            data = json.loads(raw_result)
        except json.JSONDecodeError:
            return "无法解析租赁费用计算结果，请稍后重试。"
        if data.get("error"):
            query = f"（查询内容：{data['query']}）" if data.get("query") else ""
            return f"无法计算租赁费用：{data['error']}{query}。请提供完整产品型号或设备ID。"

        def money(value: Any) -> str:
            try:
                return f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}"
            except (InvalidOperation, TypeError, ValueError):
                return str(value)

        price = money(data.get("pricePerDay"))
        rental_fee = money(data.get("rentalFee"))
        deposit = money(data.get("deposit"))
        total = money(data.get("totalAmount"))
        availability = "可租赁" if data.get("available") else "当前不可租赁或库存不足"
        return (
            "### 租赁费用明细\n\n"
            f"| 项目 | 金额/信息 |\n|---|---|\n"
            f"| 设备型号 | {str(data.get('model') or '').strip()}（ID：{data.get('droneId')}） |\n"
            f"| 日租金 | {price} 元/天 |\n"
            f"| 租赁天数 | {data.get('rentalDays')} 天 |\n"
            f"| 租金小计 | {rental_fee} 元 |\n"
            f"| 押金 | {deposit} 元 |\n"
            f"| **含押金总计** | **{total} 元** |\n"
            f"| 当前状态 | {availability}，库存 {data.get('stock')} 台 |\n\n"
            f"计算公式：{price} × {data.get('rentalDays')} + {deposit} = {total} 元。"
        )

    def _execute_tool_calls(
            self,
            db: Session,
            calls: list[dict[str, Any]],
            session_id: str,
            user_id: int,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for index, call in enumerate(calls):
            call_id = str(call.get("id") or f"call_{index}_{uuid4().hex}")
            call["id"] = call_id
            function = call.get("function") or {}
            name = str(function.get("name", ""))
            args_json = str(function.get("arguments") or "{}")
            tool = TOOL_REGISTRY.get(name) if self.mcp is None else None
            if self.mcp is None and tool is None:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"工具 {name} 不存在。",
                    }
                )
                continue
            started = time.perf_counter()
            try:
                params = json.loads(args_json)
                if self.mcp is not None:
                    output = self.mcp.call_tool(name, params, session_id, user_id)
                else:
                    output = tool.execute(db, params, user_id)
                db.add(
                    AiToolCallLog(
                        session_id=session_id,
                        user_id=user_id,
                        tool_name=name,
                        tool_input=args_json,
                        tool_output=output,
                        status=1,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                content = output
            except Exception as exc:
                db.add(
                    AiToolCallLog(
                        session_id=session_id,
                        user_id=user_id,
                        tool_name=name,
                        tool_input=args_json,
                        status=0,
                        error_msg=str(exc),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                content = f"工具 {name} 执行失败: {exc}"
            messages.append(
                {"role": "tool", "tool_call_id": call_id, "content": content}
            )
        return messages

    def _tool_definitions(self) -> list[dict[str, Any]]:
        if self.mcp is None:
            return tool_definitions(openai_format=True)
        try:
            return self.mcp.list_openai_tools()
        except Exception as exc:
            LOGGER.exception("MCP tools/list failed")
            raise BusinessException(
                ResultCode.SERVICE_UNAVAILABLE,
                "MCP服务不可用，请检查配置和运行状态",
            ) from exc

    @staticmethod
    def _save_trace(
            db: Session,
            session_id: str,
            user_id: int,
            role: str,
            content: str,
            model: str | None = None,
            token_usage: int | None = None,
            latency_ms: int | None = None,
    ) -> AiChatTrace:
        # 第一条用户消息用于更新会话标题
        if role == "user":
            prior_user_message = db.scalar(
                select(AiChatTrace.id)
                .where(
                    AiChatTrace.session_id == session_id,
                    AiChatTrace.user_id == user_id,
                    AiChatTrace.role == "user",
                )
                .limit(1)
            )
            if prior_user_message is None:
                title_trace = db.scalar(
                    select(AiChatTrace)
                    .where(
                        AiChatTrace.session_id == session_id,
                        AiChatTrace.user_id == user_id,
                        AiChatTrace.role == "system",
                    )
                    .order_by(AiChatTrace.created_time.asc())
                    .limit(1)
                )
                if title_trace and title_trace.content.strip() in {"新会话", "新对话"}:
                    title_trace.content = content.strip()
        trace = AiChatTrace(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            model=model,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )

        db.add(trace)
        db.flush()

        return trace

    def vision_chat(
            self,
            db: Session,
            session_id: str | None,
            user_id: int,
            message: str,
            filename: str,
            content_type: str | None,
            image_content: bytes,
    ) -> dict[str, Any]:

        self.ensure_enabled()

        if not self.settings.ai_vision_enabled:
            raise BusinessException(
                ResultCode.SERVICE_UNAVAILABLE,
                "图片识别功能尚未启用!静待更新!",
            )

        current_session_id = session_id or uuid4().hex
        prompt_text = (
            message.strip()
            if message and message.strip()
            else "请识别照片中的无人机型号并给出租赁建议"
        )

        del content_type

        try:
            normalized_image, normalized_mime_type = prepare_image(
                image_content,
                self.settings.ai_vision_max_image_bytes,
            )
        except ValueError as exc:
            raise BusinessException(
                ResultCode.PARAM_ERROR,
                str(exc),
            ) from exc

        # 获取数据库中的设备型号
        models = list(
            db.scalars(
                select(Drone.model)
                .where(Drone.deleted == 0)
                .order_by(Drone.id.asc())
            ).all()
        )

        model_catalog = [
            model.strip()
            for model in models
            if model and model.strip()
        ]

        if not model_catalog:
            raise BusinessException(
                ResultCode.DRONE_NOT_EXIST,
                "系统中尚未录入该无人机设备设备",
            )

        storage = get_storage(self.settings)
        object_key: str | None = None

        try:
            object_key = storage.upload(
                filename="vision.jpg",
                content=normalized_image,
                content_type=normalized_mime_type,
                object_prefix=f"users/{user_id}/ai-temp",
            )

            user_trace = self._save_trace(
                db=db,
                session_id=current_session_id,
                user_id=user_id,
                role="user",
                content=f"[图片识别] {prompt_text}",
            )

            expires_at = datetime.now() + timedelta(
                seconds=self.settings.ai_vision_image_ttl_seconds
            )

            attachment = AiImageAttachment(
                user_id=user_id,
                session_id=current_session_id,
                trace_id=user_trace.id,
                object_key=object_key,
                original_name=Path(filename).name[:255],
                mime_type=normalized_mime_type,
                size_bytes=len(normalized_image),
                expires_at=expires_at,
                deleted=0,
            )
            db.add(attachment)
            db.flush()

            image_data_url = to_data_url(
                normalized_image,
                normalized_mime_type,
            )

            catalog_text = "、".join(model_catalog)

            system_prompt = (
                "你是无人机视觉识别助手。"
                "任务是判断图片是否为无人机，识别品牌并返回最多3个候选型号。"
                "优先匹配给定型号列表，不确定时不要强行匹配。"
                "不得编造价格、库存或设备状态，只返回JSON。"
                "JSON格式:\n\n"
                "{\n"
                '  "is_drone": true,\n'
                '  "brand": "",\n'
                '  "candidate_models": [\n'
                "    {\n"
                '      "model": "",\n'
                '      "confidence": 0.0,\n'
                '      "evidence": ""\n'
                "    }\n"
                "  ],\n"
                '  "image_quality": "good|fair|poor",\n'
                '  "need_more_photos": false\n'
                "}"
            )

            user_prompt = (
                f"用户问题：{prompt_text}\n"
                "系统当前收录的无人机型号：\n" f"{catalog_text}\n"
            )

            request = {
                "model": self.settings.ai_model_vision_model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url,
                                    "detail": self.settings.ai_vision_detail,
                                },
                            },
                        ],
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": min(self.settings.ai_max_tokens, 1000),
            }

            started = time.perf_counter()
            response = self._call_api(request)
            latency_ms = int((time.perf_counter() - started) * 1000)

            response_message = (((response.get("choices") or [{}])[0].get("message")) or {})
            raw_content = response_message.get("content") or ""

            recognition = self._parse_vision_result(raw_content)

            answer = self._build_vision_answer(
                db=db,
                recognition=recognition,
            )

            self._save_trace(
                db=db,
                session_id=current_session_id,
                user_id=user_id,
                role="assistant",
                content=answer,
                model=self.settings.ai_model_vision_model,
                latency_ms=latency_ms,
            )

            db.commit()

            image_url = storage.get_access_url(object_key)

            return {
                "sessionId": current_session_id,
                "role": "assistant",
                "content": answer,
                "model": self.settings.ai_model_vision_model,
                "createdTime": datetime.now(),
                "recognition": recognition,
                "attachment": {
                    "id": attachment.id,
                    "type": "image",
                    "url": image_url,
                    "expiresAt": expires_at,
                },
            }

        except BusinessException:
            db.rollback()
            if object_key:
                storage.delete(object_key)
            raise
        except Exception as exc:
            db.rollback()
            if object_key:
                storage.delete(object_key)

            LOGGER.exception("无人机图片识别失败")

            raise BusinessException(
                ResultCode.SERVICE_UNAVAILABLE,
                "图片识别服务暂时不可用，请稍后重试",
            ) from exc

    @staticmethod
    def _parse_vision_result(
            raw_content: str,
    ) -> dict[str, Any]:
        # 解析 deepseek-v4-flash-vision-exp 模型返回值，并对字段进行安全归一化
        cleaned = raw_content.strip()

        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise BusinessException(
                ResultCode.SERVICE_UNAVAILABLE,
                "视觉模型返回了无法解析的结果",
            ) from exc

        if not isinstance(data, dict):
            raise BusinessException(
                ResultCode.SERVICE_UNAVAILABLE,
                "视觉模型返回格式错误",
            )

        raw_candidates = data.get("candidate_models")
        if not isinstance(raw_candidates, list):
            raw_candidates = []

        candidates: list[dict[str, Any]] = []

        for raw_candidate in raw_candidates[:3]:
            if not isinstance(raw_candidate, dict):
                continue

            model = str(raw_candidate.get("model") or "").strip()
            if not model:
                continue

            try:
                confidence = float(
                    raw_candidate.get("confidence", 0)
                )
            except (TypeError, ValueError):
                confidence = 0.0

            confidence = max(0.0, min(confidence, 1.0))

            candidates.append(
                {
                    "model": model,
                    "confidence": confidence,
                    "evidence": str(
                        raw_candidate.get("evidence") or "未提供"
                    ).strip(),
                }
            )

        candidates.sort(
            key=lambda item: item["confidence"],
            reverse=True,
        )

        image_quality = str(
            data.get("image_quality") or "poor"
        ).strip().lower()

        if image_quality not in {"good", "fair", "poor"}:
            image_quality = "poor"

        return {
            "is_drone": data.get("is_drone") is True,
            "brand": str(data.get("brand") or "").strip(),
            "candidate_models": candidates,
            "image_quality": image_quality,
            "need_more_photos": (
                    data.get("need_more_photos") is True
            ),
        }

    def _build_vision_answer(
            self,
            db: Session,
            recognition: dict[str, Any],
    ) -> str:
        # 视觉识别可信度 + 数据库记录 = 最终回答
        if not recognition["is_drone"]:
            return (
                "### 图片识别结果\n\n"
                "没有可靠识别到无人机。\n\n"
                "请上传包含完整机身、机臂、云台或型号铭牌的清晰照片。"
            )

        candidates = recognition["candidate_models"]

        if not candidates:
            return (
                "### 图片识别结果\n\n"
                "图片中包含无人机，但暂时无法判断具体型号。\n\n"
                "建议补拍以下照片：\n\n"
                "- 无人机正面和顶部\n"
                "- 机身品牌或型号标识\n"
                "- 云台和避障传感器\n"
                "- 机身底部铭牌"
            )

        best_candidate = candidates[0]
        confidence = best_candidate["confidence"]

        if confidence >= 0.80:
            return self._build_high_confidence_answer(
                db=db,
                candidate=best_candidate,
                recognition=recognition,
            )

        if confidence >= 0.50:
            return self._build_medium_confidence_answer(
                db=db,
                candidates=candidates,
                recognition=recognition,
            )

        return self._build_low_confidence_answer(
            candidates=candidates,
            recognition=recognition,
        )

    def _build_high_confidence_answer(
            self,
            db: Session,
            candidate: dict[str, Any],
            recognition: dict[str, Any],
    ) -> str:
        candidate_model = candidate["model"]

        drone, match_type = resolve_drone_by_model(
            db,
            candidate_model,
        )

        # 通过模糊相似度匹配得到的近似设备 不直接推荐
        if drone is None or match_type == "fuzzy_model":
            return (
                "### 图片识别结果\n\n"
                f"照片中的无人机可能是：{candidate_model}\n\n"
                f"识别参考置信度是：{candidate['confidence']:.0%}\n"
                "该结果无法与系统中的具体设备型号可靠匹配，"
                "暂时不能提供库存和价格信息。\n\n"
                "请确认机身铭牌上的完整型号，或者重新拍摄型号标识。"
            )

        return self._format_vision_recommendation(
            db=db,
            drone=drone,
            confidence=candidate["confidence"],
            evidence=candidate["evidence"],
            image_quality=recognition["image_quality"],
        )

    def _build_medium_confidence_answer(
            self,
            db: Session,
            candidates: list[dict[str, Any]],
            recognition: dict[str, Any],
    ) -> str:
        rows: list[str] = []

        for candidate in candidates[:3]:
            drone, match_type = resolve_drone_by_model(
                db,
                candidate["model"],
            )

            if drone is not None and match_type != "fuzzy_model":
                display_model = drone.model.strip()
            else:
                display_model = candidate["model"]

            rows.append(
                f"| {display_model} | "
                f"{candidate['confidence']:.0%} | "
                f"{candidate['evidence']} |"
            )

        quality_names = {
            "good": "良好",
            "fair": "一般",
            "poor": "较差",
        }

        table = "\n".join(rows)

        return (
            "### 图片识别结果\n\n"
            "图片中识别到了无人机，但暂时无法可靠确认具体型号。\n\n"
            f"- 图片质量：{quality_names[recognition['image_quality']]}\n"
            "- 请从以下候选型号中确认：\n\n"
            "| 候选型号 | 参考置信度 | 判断依据 |\n"
            "|---|---:|---|\n"
            f"{table}\n\n"
            "您需要的候选型号，确认后系统将为您查询真实库存、价格和押金。"
        )

    @staticmethod
    def _build_low_confidence_answer(
            candidates: list[dict[str, Any]],
            recognition: dict[str, Any],
    ) -> str:
        best = candidates[0]

        quality_names = {
            "good": "良好",
            "fair": "一般",
            "poor": "较差",
        }

        return (
            "### 图片识别结果\n\n"
            "目前无法可靠判断照片中的具体无人机型号。\n\n"
            f"- 最接近的候选：{best['model']}\n"
            f"- 参考置信度：{best['confidence']:.0%}\n"
            f"- 图片质量：{quality_names[recognition['image_quality']]}\n\n"
            "为了避免推荐错误设备，请重新上传包含以下内容的照片：\n\n"
            "完整机身、机身顶部或侧面的型号文字、云台摄像头、底部铭牌型号标识"
        )

    def _format_vision_recommendation(
            self,
            db: Session,
            drone: Drone,
            confidence: float,
            evidence: str,
            image_quality: str,
    ) -> str:
        model = (drone.model or "").strip()
        brand = (drone.brand or "-").strip()
        drone_type = (drone.type or "-").strip()

        available = (
                drone.deleted == 0
                and drone.on_shelf == 1
                and drone.status == 1
                and drone.stock > 0
        )

        if available:
            rental_status = "当前可以租赁"
            recommendation = (
                f"推荐选择 {model}。"
                "具体价格和库存来自当前数据库。"
            )
        elif drone.on_shelf != 1:
            rental_status = "设备已下架"
            recommendation = self._format_alternative_recommendations(
                db,
                drone,
            )
        elif drone.status != 1:
            rental_status = "设备状态异常"
            recommendation = self._format_alternative_recommendations(
                db,
                drone,
            )
        else:
            rental_status = "当前库存不足"
            recommendation = self._format_alternative_recommendations(
                db,
                drone,
            )

        quality_names = {
            "good": "良好",
            "fair": "一般",
            "poor": "较差",
        }

        return (
            "### 图片识别结果\n\n"
            f"照片中的无人机可能是：{model}\n\n"
            "| 项目 | 识别或系统信息 |\n"
            "|---|---|\n"
            f"| 参考置信度 | {confidence:.0%} |\n"
            f"| 图片质量 | {quality_names[image_quality]} |\n"
            f"| 判断依据 | {evidence} |\n"
            f"| 品牌 | {brand} |\n"
            f"| 型号 | {model} |\n"
            f"| 类型 | {drone_type} |\n"
            f"| 日租金 | {drone.price_per_day:.2f} 元/天 |\n"
            f"| 押金 | {drone.deposit:.2f} 元 |\n"
            f"| 库存 | {drone.stock} 台 |\n"
            f"| 上架状态 | "
            f"{'已上架' if drone.on_shelf == 1 else '已下架'} |\n"
            f"| 设备状态 | "
            f"{'正常' if drone.status == 1 else '异常'} |\n"
            f"| 租赁状态 | {rental_status} |\n\n"
            f"### 推荐结果\n\n{recommendation}\n\n"
            "> 图片识别可能受到拍摄角度、光线和相似机型外观的影响。"
            "下单前请核对机身铭牌上的完整型号。"
        )

    @staticmethod
    def _format_alternative_recommendations(
            db: Session,
            identified_drone: Drone,
    ) -> str:
        conditions = [
            Drone.deleted == 0,
            Drone.on_shelf == 1,
            Drone.status == 1,
            Drone.stock > 0,
            Drone.id != identified_drone.id,
        ]

        if identified_drone.type:
            conditions.append(
                Drone.type == identified_drone.type
            )

        alternatives = list(
            db.scalars(
                select(Drone)
                .where(*conditions)
                .order_by(
                    Drone.price_per_day.asc(),
                    Drone.stock.desc(),
                )
                .limit(3)
            ).all()
        )

        if not alternatives:
            return (
                "该型号当前暂不可租赁，且系统中暂时没有同类型的可租赁替代设备。"
            )

        rows = "\n".join(
            (
                f"- **{item.model.strip()}**："
                f"{item.price_per_day:.2f} 元/天，"
                f"押金 {item.deposit:.2f} 元，"
                f"库存 {item.stock} 台"
            )
            for item in alternatives
        )

        return (
            "识别出的型号当前暂不可租赁，可以考虑以下同类型在租设备：\n\n"
            f"{rows}"
        )

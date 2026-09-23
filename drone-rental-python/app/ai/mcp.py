"""Standard MCP server and client adapters for the AI business tools."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..config import Settings
from ..models import AiToolCallLog
from .tools import TOOL_REGISTRY
from ..redis import get_redis_support



class McpToolError(RuntimeError):
    """Raised when an MCP connection or remote tool call fails."""


class McpApiKeyMiddleware:
    """Protect the MCP transport with a deployment-level shared secret."""

    def __init__(self, app: ASGIApp, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            authorization = headers.get("authorization", "")
            bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
            legacy_key = headers.get("x-mcp-api-key", "")
            provided = bearer or legacy_key
            if not provided or not secrets.compare_digest(provided, self.api_key):
                response = JSONResponse(
                    {"error": "Invalid MCP API key"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _create_user_context_token(settings: Settings, user_id: int, tool_name: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "purpose": "mcp-tool-user-context",
            "scope": f"mcp:tool:{tool_name}",
            "jti": secrets.token_urlsafe(24),
            "iat": now,
            "exp": now + timedelta(seconds=60),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def _read_request_meta(context: Context) -> dict[str, Any]:
    meta = context.request_context.meta
    return meta.model_dump(by_alias=True, exclude_none=True) if meta is not None else {}


def _verify_internal_user(settings: Settings, meta: dict[str, Any], tool_name: str) -> tuple[int, bool]:
    token = str(meta.get("droneRentalUserToken") or "")
    if not token:
        return 0, False
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                             options={"require": ["sub","purpose","scope","jti","iat","exp",]})

        user_id = int(payload["sub"])
        purpose = str(payload["purpose"])
        scope = str(payload["scope"])
        jti = str(payload["jti"])

        expected_scope = f"mcp:tool:{tool_name}"

        if user_id <= 0:
            raise ValueError("invalid user id")

        if purpose != "mcp-tool-user-context":
            raise ValueError("invalid token purpose")

        if not secrets.compare_digest(scope, expected_scope):
            raise PermissionError("MCP 令牌无权调用当前工具")

        if not jti:
            raise ValueError("missing jti")

    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise PermissionError("invalid MCP token") from exc

    redis_support = get_redis_support()

    consumed = redis_support.acquire_once(
        f"mcp-replay:{jti}",
        ttl_seconds=65,
    )

    # Redis 不可用
    if consumed is False:
        raise RuntimeError("MCP anti-replay service is unavailable.")

    # Key 已存在，令牌重放
    if consumed is None:
        raise PermissionError("Detected the reuse of the MCP token")

    return user_id, True



@dataclass(slots=True)
class McpRuntime:
    """Objects needed to mount and manage the embedded MCP server."""

    server: FastMCP
    app: ASGIApp


def create_mcp_runtime(
    settings: Settings,
    session_factory: sessionmaker[Session]
) -> McpRuntime:
    """Create the standards-compliant Streamable HTTP MCP application."""
    if not settings.ai_mcp_api_key:
        raise ValueError("AI_MCP_API_KEY must be configured when MCP is enabled")

    server = FastMCP(
        "drone-rental",
        instructions="无人机租赁系统只读业务工具。",
        json_response=True,
        stateless_http=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.mcp_allowed_hosts,
            allowed_origins=settings.mcp_allowed_origins,
        ),
    )

    def execute(tool_name: str, params: dict[str, Any], context: Context) -> str:
        meta = _read_request_meta(context)
        user_id, is_internal = _verify_internal_user(settings, meta, tool_name)
        session_id = (
            str(meta.get("droneRentalSessionId") or "mcp-internal")
            if is_internal
            else "mcp-external"
        )
        tool = TOOL_REGISTRY[tool_name]
        started = time.perf_counter()
        with session_factory() as db:
            try:
                output = tool.execute(db, params, user_id)
                if not is_internal:
                    db.add(
                        AiToolCallLog(
                            session_id=session_id,
                            user_id=user_id,
                            tool_name=tool_name,
                            tool_input=json.dumps(params, ensure_ascii=False),
                            tool_output=output,
                            status=1,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    db.commit()
                return output
            except Exception as exc:
                db.rollback()
                if not is_internal:
                    db.add(
                        AiToolCallLog(
                            session_id=session_id,
                            user_id=user_id,
                            tool_name=tool_name,
                            tool_input=json.dumps(params, ensure_ascii=False),
                            status=0,
                            error_msg=str(exc),
                            latency_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    db.commit()
                raise

    @server.tool(
        name="query_drones",
        description=TOOL_REGISTRY["query_drones"].description,
        structured_output=False,
    )
    def query_drones(
        context: Context,
        keyword: Annotated[
            str | None,
            Field(min_length=1, description="型号、品牌、类型或描述关键词，支持模糊匹配"),
        ] = None,
        brand: Annotated[
            str | None,
            Field(min_length=1, description="品牌关键词，支持中英文别名，如 DJI 或大疆"),
        ] = None,
        drone_type: Annotated[
            str | None,
            Field(min_length=1, description="用途/类型关键词，如航拍、测绘或农业"),
        ] = None,
        maxPrice: Annotated[
            float | None,
            Field(ge=0, description="最高日租金，单位为人民币元"),
        ] = None,
    ) -> str:
        params = {
            key: value
            for key, value in {
                "keyword": keyword,
                "brand": brand,
                "drone_type": drone_type,
                "maxPrice": maxPrice,
            }.items()
            if value is not None
        }
        return execute("query_drones", params, context)

    @server.tool(
        name="query_orders",
        description=TOOL_REGISTRY["query_orders"].description,
        structured_output=False,
    )
    def query_orders(
        context: Context,
        status: Annotated[
            Literal[0, 1, 2, 3, 4, 5, 6, 7, 8] | None,
            Field(description="订单状态：0待支付至8待商家收货"),
        ] = None,
    ) -> str:
        params = {"status": status} if status is not None else {}
        return execute("query_orders", params, context)

    @server.tool(
        name="check_qualification",
        description=TOOL_REGISTRY["check_qualification"].description,
        structured_output=False,
    )
    def check_qualification(context: Context) -> str:
        return execute("check_qualification", {}, context)

    @server.tool(
        name="guide_fault_report",
        description=TOOL_REGISTRY["guide_fault_report"].description,
        structured_output=False,
    )
    def guide_fault_report(
        context: Context,
        droneModel: Annotated[
            str | None,
            Field(min_length=1, description="故障无人机型号"),
        ] = None,
        faultType: Annotated[
            Literal["hardware", "software", "battery", "gimbal", "flight", "other"] | None,
            Field(description="故障类型代码"),
        ] = None,
    ) -> str:
        params = {
            key: value
            for key, value in {"droneModel": droneModel, "faultType": faultType}.items()
            if value is not None
        }
        return execute("guide_fault_report", params, context)

    @server.tool(
        name="recommend_drone",
        description=TOOL_REGISTRY["recommend_drone"].description,
        structured_output=False,
    )
    def recommend_drone(
        context: Context,
        purpose: Annotated[
            str | None,
            Field(min_length=1, description="使用场景，如航拍、测绘、旅行或短视频"),
        ] = None,
        brand: Annotated[
            str | None,
            Field(min_length=1, description="品牌偏好，支持中英文别名，如 DJI 或大疆"),
        ] = None,
        budget: Annotated[
            float | None,
            Field(ge=0, description="每日预算上限，人民币元；0表示不限"),
        ] = None,
    ) -> str:
        params = {
            key: value
            for key, value in {"purpose": purpose, "brand": brand, "budget": budget}.items()
            if value is not None
        }
        return execute("recommend_drone", params, context)

    @server.tool(
        name="check_airspace",
        description=TOOL_REGISTRY["check_airspace"].description,
        structured_output=False,
    )
    def check_airspace(context: Context) -> str:
        return execute("check_airspace", {}, context)

    @server.tool(
        name="calculate_rental_price",
        description=TOOL_REGISTRY["calculate_rental_price"].description,
        structured_output=False,
    )
    def calculate_rental_price(
        rentalDays: Annotated[int, Field(ge=1, description="租赁天数，必须大于0")],
        context: Context,
        droneId: Annotated[
            int | None,
            Field(ge=1, description="仅当用户明确提供数据库ID时传入"),
        ] = None,
        droneModel: Annotated[
            str | None,
            Field(min_length=1, description="完整或可唯一识别的产品型号"),
        ] = None,
    ) -> str:
        params: dict[str, Any] = {"rentalDays": rentalDays}
        if droneId is not None:
            params["droneId"] = droneId
        if droneModel is not None:
            params["droneModel"] = droneModel
        return execute("calculate_rental_price", params, context)

    mcp_app = server.streamable_http_app()
    return McpRuntime(server=server, app=McpApiKeyMiddleware(mcp_app, settings.ai_mcp_api_key))


class McpToolClient:
    """Synchronous facade over the official asynchronous MCP client."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def list_openai_tools(self) -> list[dict[str, Any]]:
        return asyncio.run(self._list_openai_tools())

    async def _list_openai_tools(self) -> list[dict[str, Any]]:
        async with self._session() as session:
            response = await session.list_tools()
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in response.tools
            ]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        session_id: str,
        user_id: int,
    ) -> str:
        return asyncio.run(self._call_tool(name, arguments, session_id, user_id))

    async def _call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        session_id: str,
        user_id: int,
    ) -> str:
        meta = {
            "droneRentalSessionId": session_id,
            "droneRentalUserToken": _create_user_context_token(self.settings, user_id, name),
        }
        async with self._session() as session:
            result = await session.call_tool(name, arguments, meta=meta)
        content = "\n".join(
            block.text
            for block in result.content
            if getattr(block, "type", None) == "text"
        )
        if result.isError:
            raise McpToolError(content or f"MCP tool failed: {name}")
        return content

    @asynccontextmanager
    async def _session(self):
        headers = {"Authorization": "Bearer " + self.settings.ai_mcp_api_key}
        timeout = httpx.Timeout(self.settings.ai_mcp_timeout_seconds)
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        ) as http_client:
            async with streamable_http_client(
                self.settings.ai_mcp_server_url,
                http_client=http_client,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

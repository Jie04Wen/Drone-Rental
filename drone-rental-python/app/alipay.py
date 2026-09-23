"""Minimal Alipay RSA2 client corresponding to Java AlipayClient."""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .config import Settings

import logging

logger = logging.getLogger(__name__)

class AlipayClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def create_page_pay(
        self,
        order_no: str,
        subject: str,
        total_amount: str,
        return_url: str | None,
        time_expire: datetime | None = None,
    ) -> str | None:
        if not self.settings.alipay_enabled:
            return None
        try:
            business = {
                "out_trade_no": order_no,
                "total_amount": total_amount,
                "subject": subject,
                "product_code": "FAST_INSTANT_TRADE_PAY",
            }
            if time_expire is not None:
                business["time_expire"] = time_expire.strftime("%Y-%m-%d %H:%M:%S")
            params = self._signed_params("alipay.trade.page.pay", json.dumps(business, ensure_ascii=False), return_url=return_url)
            # Preserves the Java ordering: return_url is appended after signing.
            biz_content = params.pop("biz_content")
            query_string = urlencode(params, encoding=self.settings.alipay_charset)
            action_url = (
                f"{self.settings.alipay_gateway_url}"
                f"?{query_string}"
            )
            inputs = (
                "<input type='hidden' "
                "name='biz_content' "
                f"value='{html.escape(biz_content, quote=True)}' />"
            )
            return (
                "<form "
                "id='alipay_form' "
                f"action='{html.escape(action_url, quote=True)}' "
                "method='POST' "
                f"accept-charset='{html.escape(self.settings.alipay_charset)}'>"
                f"{inputs}"
                "<input type='submit' "
                "value='正在跳转到支付宝...' "
                "style='display:none;' />"
                "</form>"
                "<script>"
                "document.getElementById('alipay_form').submit();"
                "</script>"
            )
        except Exception:
            return None

    def query_trade(self, order_no: str) -> dict[str, Any]:
        if not self.settings.alipay_enabled:
            return {}
        try:
            params = self._signed_params(
                "alipay.trade.query", json.dumps({"out_trade_no": order_no}, ensure_ascii=False)
            )
            response = httpx.get(
                self.settings.alipay_gateway_url,
                params=params,
                timeout=httpx.Timeout(15, connect=5),
            )
            response.raise_for_status()
            root = response.json()
            node = (
                root.get("alipay_trade_query_response")
                or root.get("alipay_trade_query_Response")
                or root.get("alipay_trade_queryresponse")
            )
            if node and str(node.get("code")) == "10000":
                return {
                    "tradeNo": node.get("trade_no", ""),
                    "tradeStatus": node.get("trade_status", ""),
                    "totalAmount": node.get("total_amount", ""),
                }
        except Exception:
            return {}
        return {}

    def refund(
        self, order_no: str, amount: str, reason: str | None, request_no: str | None = None
    ) -> dict[str, Any]:
        if not self.settings.alipay_enabled:
            return {}
        try:
            params = self._signed_params(
                "alipay.trade.refund",
                json.dumps(
                    {
                        "out_trade_no": order_no,
                        "refund_amount": amount,
                        "refund_reason": reason or "用户申请退款",
                        "out_request_no": request_no or f"REFUND-{order_no}",
                    },
                    ensure_ascii=False,
                ),
            )
            response = httpx.get(
                self.settings.alipay_gateway_url,
                params=params,
                timeout=httpx.Timeout(15, connect=5),
            )
            response.raise_for_status()
            root = response.json()
            node = (
                root.get("alipay_trade_refund_response")
                or root.get("alipay_trade_refund_Response")
                or root.get("alipay_trade_refundresponse")
            )
            if node and str(node.get("code")) == "10000":
                return {"tradeNo": node.get("trade_no", ""), "refundFee": node.get("refund_fee", "")}
        except Exception:
            return {}
        return {}

    def verify_notify(self, params: dict[str, str]) -> bool:
        if not self.settings.alipay_enabled:
            return True
        try:
            signature = params.get("sign")
            if not signature:
                return False
            content = "&".join(
                f"{key}={value}"
                for key, value in sorted(params.items())
                if value and key not in {"sign", "sign_type"}
            )
            public_key = self._load_public_key(self.settings.alipay_public_key)
            public_key.verify(
                base64.b64decode(signature),
                content.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            logger.exception("支付宝异步通知验签失败")
            return False

    def _signed_params(self, method: str, business_content: str, return_url: str | None = None) -> dict[str, str]:
        params = {
            "app_id": self.settings.alipay_app_id,
            "method": method,
            "format": self.settings.alipay_format,
            "charset": self.settings.alipay_charset,
            "sign_type": self.settings.alipay_sign_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": business_content,
        }
        if self.settings.alipay_notify_url:
            params["notify_url"] = self.settings.alipay_notify_url
        if return_url:
            params["return_url"] = return_url
        content = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
        private_key = self._load_private_key(self.settings.alipay_private_key)
        signature = private_key.sign(content.encode("utf-8"),padding.PKCS1v15(),hashes.SHA256(),)
        params["sign"] = base64.b64encode(signature).decode("ascii")
        return params

    @staticmethod
    def _load_private_key(value: str):
        data = value.encode("ascii")
        if b"BEGIN" in data:
            return serialization.load_pem_private_key(data, password=None)
        return serialization.load_der_private_key(base64.b64decode(data), password=None)

    @staticmethod
    def _load_public_key(value: str):
        data = value.encode("ascii")
        if b"BEGIN" in data:
            return serialization.load_pem_public_key(data)
        return serialization.load_der_public_key(base64.b64decode(data))

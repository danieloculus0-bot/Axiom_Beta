"""JobBOSS2 Public API write adapter (OAuth2, POST and PATCH, no direct SQL writes)."""
from __future__ import annotations

import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import ExternalRecord, PushReceipt
from .vendor_http import VendorError, VendorHTTP, records


class JobBoss2WriteAdapter(VendorHTTP):
    default_base_url = "https://api-jb2.integrations.ecimanufacturing.com"

    def __init__(self, config, credentials=None, *, transport=None):
        super().__init__(config, credentials, transport=transport)
        self.config = dict(config)
        self.config.setdefault("read_routes", {
            "sales_order": "/api/v1/orders",
            "quote": "/api/v1/quotes",
            "customer": "/api/v1/customers",
            "estimate": "/api/v1/estimates",
            "time_ticket": "/api/v1/time-tickets",
            "time_ticket_detail": "/api/v1/time-ticket-details",
            "order_routing": "/api/v1/order-routings",
        })
        self.config.setdefault("write_routes", {
            "sales_order": {"create": "/api/v1/orders", "update": "/api/v1/orders/{orderNumber}"},
            "quote": {"create": "/api/v1/quotes", "update": "/api/v1/quotes/{quoteNumber}"},
            "customer": {"create": "/api/v1/customers", "update": "/api/v1/customers/{customerCode}"},
            "estimate": {"create": "/api/v1/estimates", "update": "/api/v1/estimates/{partNumber}"},
            "time_ticket": {"create": "/api/v1/time-tickets",
                            "update": "/api/v1/time-tickets/{ticketDate}/employees/{employeeCode}"},
            "time_ticket_detail": {"create": "/api/v1/time-ticket-details",
                                   "update": "/api/v1/time-ticket-details/{timeTicketGUID}"},
            "order_routing": {
                "create": "/api/v1/orders/{orderNumber}/order-line-items/{itemNumber}/order-routings",
                "update": "/api/v1/orders/{orderNumber}/order-line-items/{itemNumber}/order-routings/{stepNumber}",
            },
        })
        self.config.setdefault("id_fields", {
            "sales_order": "orderNumber", "quote": "quoteNumber",
            "customer": "customerCode", "estimate": "partNumber",
            "time_ticket": "uniqueID", "time_ticket_detail": "timeTicketGUID",
            "order_routing": "uniqueID",
        })
        self.config.setdefault("records_key", "Data")
        self._cached_token = ""
        self._token_expiration = 0.0

    def _base_url(self):
        base = super()._base_url()
        if base != self.default_base_url:
            raise VendorError("Only the official JobBOSS2 Public API host is allowed")
        return base

    def _token(self):
        if self.credentials.get("token"):
            return str(self.credentials["token"])
        if self._cached_token and time.monotonic() < self._token_expiration:
            return self._cached_token
        client_id = self.credentials.get("client_id") or os.getenv("AXIOM_JB2_CLIENT_ID")
        secret = self.credentials.get("client_secret") or os.getenv("AXIOM_JB2_CLIENT_SECRET")
        if not client_id or not secret:
            raise VendorError("JobBOSS2 API client credentials are not configured")
        token_url = "https://api-user.integrations.ecimanufacturing.com/oauth2/api-user/token"
        data = urlencode({"grant_type": "client_credentials", "scope": "openid",
                          "client_id": client_id, "client_secret": secret}).encode("ascii")
        req = Request(token_url, data=data, method="POST",
                      headers={"Content-Type": "application/x-www-form-urlencoded",
                               "Accept": "application/json"})
        try:
            with self.transport(req, timeout=float(self.config.get("timeout", 20))) as response:
                result = json.load(response)
        except Exception:
            raise VendorError("JobBOSS2 OAuth token request failed") from None
        token = result.get("access_token") if isinstance(result, dict) else None
        if not token:
            raise VendorError("JobBOSS2 OAuth token missing")
        lifetime = max(1, int(result.get("expires_in") or 3600) - 90)
        self._cached_token = str(token)
        self._token_expiration = time.monotonic() + lifetime
        return self._cached_token

    def pull(self, entity_type, *, cursor=""):
        detail = {
            "sales_order": ("/api/v1/orders/", "orderNumber"),
            "quote": ("/api/v1/quotes/", "quoteNumber"),
            "customer": ("/api/v1/customers/", "customerCode"),
            "estimate": ("/api/v1/estimates/", "partNumber"),
            "time_ticket_detail": ("/api/v1/time-ticket-details/", "timeTicketGUID"),
        }
        if cursor and entity_type in detail:
            from .vendor_http import safe_segment
            prefix, id_field = detail[entity_type]
            data = self._http("GET", prefix + safe_segment(cursor))
            if isinstance(data, dict) and isinstance(data.get("Data"), dict):
                data = data["Data"]
            if not isinstance(data, dict):
                raise VendorError("Expected JobBOSS2 detail object")
            return [ExternalRecord(str(data.get(id_field) or cursor), entity_type, data)]
        if cursor:
            raise VendorError("Exact-record read requires a supported detail route")
        return super().pull(entity_type, cursor="")

    def push(self, entity_type, operation, payload):
        if operation == "delete":
            return PushReceipt(False, message="JobBOSS2 Public API does not support delete")
        return super().push(entity_type, operation, payload)

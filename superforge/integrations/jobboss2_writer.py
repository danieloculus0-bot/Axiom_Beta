"""JobBOSS2 Public API write adapter (OAuth2, POST and PATCH, no direct SQL writes)."""
from __future__ import annotations

import json
import os
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
        })
        self.config.setdefault("write_routes", {
            "sales_order": {"create": "/api/v1/orders", "update": "/api/v1/orders/{orderNumber}"},
        })
        self.config.setdefault("id_fields", {"sales_order": "orderNumber"})
        self.config.setdefault("records_key", "Data")

    def _base_url(self):
        base = super()._base_url()
        if base != self.default_base_url:
            raise VendorError("Only the official JobBOSS2 Public API host is allowed")
        return base

    def _token(self):
        if self.credentials.get("token"):
            return str(self.credentials["token"])
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
        return str(token)

    def pull(self, entity_type, *, cursor=""):
        if cursor and entity_type == "sales_order":
            from .vendor_http import safe_segment
            data = self._http("GET", "/api/v1/orders/" + safe_segment(cursor))
            if not isinstance(data, dict):
                raise VendorError("Expected JobBOSS2 order object")
            return [ExternalRecord(str(data.get("orderNumber") or cursor), entity_type, data)]
        return super().pull(entity_type, cursor=cursor)

    def push(self, entity_type, operation, payload):
        if operation == "delete":
            return PushReceipt(False, message="JobBOSS2 Public API does not support delete")
        return super().push(entity_type, operation, payload)

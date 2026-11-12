"""HTTP primitives for vendor adapters. Credentials remain local to the caller."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .base import ERPAdapter, ExternalRecord, PushReceipt


class VendorError(RuntimeError):
    pass


def safe_segment(value):
    value = str(value).strip()
    if not value or value in {".", ".."}:
        raise ValueError("a nonempty external record identifier is required")
    return quote(value, safe="")


def records(data, *, key=None):
    """No silent success on an unexpected vendor response shape."""
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        if key:
            rows = data.get(key)
        else:
            matches = [data[k] for k in ("Data", "data", "items", "results", "records")
                       if isinstance(data.get(k), list)]
            if len(matches) != 1:
                raise VendorError("Unrecognized collection envelope; configure records_key")
            rows = matches[0]
    else:
        raise VendorError("Expected a JSON collection")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise VendorError("Expected a list of object records")
    return rows


class VendorHTTP(ERPAdapter):
    """HTTP transport with exact route templates and opt-in outbound mutations."""
    default_base_url = ""
    auth_scheme = "Bearer"

    def __init__(self, config, credentials=None, *, transport=None):
        super().__init__(config, credentials)
        self.transport = transport or urlopen

    def _base_url(self):
        base = str(self.config.get("base_url") or self.default_base_url).rstrip("/")
        uri = urlsplit(base)
        if uri.scheme != "https" or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
            raise ValueError("An HTTPS vendor base_url is required")
        return base

    def _token(self):
        token = self.credentials.get("token") or self.credentials.get("api_token")
        if not token:
            raise VendorError("Vendor API token is not configured")
        return str(token)

    def _http(self, method, path, payload=None):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ValueError("Vendor route must be a root-relative path")
        headers = {"Accept": "application/json", "Authorization": self.auth_scheme + " " + self._token()}
        body = None
        if payload is not None:
            if not isinstance(payload, dict):
                raise ValueError("Vendor write requires a JSON object")
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        req = Request(self._base_url() + path, data=body, method=method, headers=headers)
        try:
            with self.transport(req, timeout=float(self.config.get("timeout", 20))) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            # Do not echo URLs, tokens, full vendor responses or private records into logs.
            status = getattr(exc, "code", None)
            raise VendorError("Vendor request failed" + (f" (HTTP {status})" if status else "")) from None
        except (ValueError, UnicodeDecodeError):
            raise VendorError("Vendor response was not valid JSON") from None

    def _route(self, entity_type, operation, payload=None):
        source = self.config.get("read_routes") if operation == "read" else self.config.get("write_routes")
        template = (source or {}).get(entity_type, {})
        if isinstance(template, dict):
            template = template.get(operation)
        if not isinstance(template, str) or not template.startswith("/"):
            raise VendorError(f"No configured {operation} route for {entity_type}")
        fields = payload or {}
        # Only known placeholders can be replaced and each value becomes one safe URL segment.
        import re
        needed = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template)
        for field in needed:
            if field not in fields:
                raise VendorError(f"Route identifier {field} is required")
            template = template.replace("{" + field + "}", safe_segment(fields[field]))
        if "{" in template or "}" in template or template.startswith("//"):
            raise VendorError("Invalid route template")
        return template

    def pull(self, entity_type, *, cursor=""):
        params = {"id": cursor, "external_id": cursor} if cursor else {}
        path = self._route(entity_type, "read", params)
        data = self._http("GET", path)
        if isinstance(data, dict) and cursor:
            items = [data]
        else:
            items = records(data, key=self.config.get("records_key"))
        id_field = (self.config.get("id_fields") or {}).get(entity_type, "id")
        result = []
        for item in items:
            identifier = item.get(id_field)
            if identifier is None or str(identifier).strip() == "":
                raise VendorError(f"Vendor record missing {id_field}")
            result.append(ExternalRecord(str(identifier), entity_type, item))
        return result

    def push(self, entity_type, operation, payload):
        if operation not in {"create", "update"}:
            return PushReceipt(False, message="Only create/update are supported")
        if not self.config.get("allow_writes", False):
            return PushReceipt(False, message="Writes disabled for this vendor connection")
        if not isinstance(payload, dict) or not payload:
            return PushReceipt(False, message="A mapped write payload is required")
        route = self._route(entity_type, operation, payload)
        body = {k: v for k, v in payload.items() if k not in (self.config.get("route_only_fields") or [])}
        method = "POST" if operation == "create" else self.config.get("update_method", "PATCH")
        if method not in ({"POST"} if operation == "create" else {"PATCH", "PUT"}):
            raise VendorError("Unsupported HTTP write method")
        data = self._http(method, route, body)
        field = (self.config.get("id_fields") or {}).get(entity_type, "id")
        external_id = (data.get(field) if isinstance(data, dict) else None) or payload.get(field) or payload.get("external_id") or ""
        return PushReceipt(True, str(external_id), "Vendor accepted request", {"status": "accepted"})


class MyTrackAdapter(VendorHTTP):
    """MyTrack mapping shell. Vendor product, paths and permissions MUST be provided.

    No MyTrack endpoint is assumed; an unrelated product with the same name
    must not become a pretend live integration.
    """
    def _route(self, entity_type, operation, payload=None):
        if not self.config.get("mytrack_interface_verified"):
            raise VendorError("MyTrack interface not verified; configure approved vendor API")
        return super()._route(entity_type, operation, payload)

    def _base_url(self):
        if not self.config.get("mytrack_interface_verified"):
            raise VendorError("MyTrack interface not verified; configure approved vendor API")
        return super()._base_url()

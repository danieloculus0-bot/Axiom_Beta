"""Paperless Parts and Fulcrum adapters for a configurable quoting-to-ERP bridge."""
from __future__ import annotations

from urllib.parse import urlencode

from .base import ExternalRecord, PushReceipt
from .vendor_http import VendorError, VendorHTTP, records, safe_segment


class PaperlessPartsAdapter(VendorHTTP):
    default_base_url = "https://api.paperlessparts.com"
    auth_scheme = "API-Token"

    def _base_url(self):
        # Paperless Parts' public REST API endpoint, not Fulcrum's endpoint.
        return super()._base_url()

    def pull(self, entity_type, *, cursor=""):
        if entity_type not in {"quote", "order"}:
            raise ValueError("Paperless Parts supports quote and order imports")
        plural = "quotes" if entity_type == "quote" else "orders"
        if cursor:
            # Cursor can select an exact externally numbered record.
            path = f"/{plural}/public/{safe_segment(cursor)}"
            item = self._http("GET", path)
            if not isinstance(item, dict):
                raise VendorError("Expected quote or order object")
            return [ExternalRecord(str(item.get("number") or cursor), entity_type, item)]

        # New-records feed is read first, then the full details are fetched.
        # A bounded batch avoids unbounded fan-out on first startup.
        index = self._http("GET", f"/{plural}/public/new")
        entries = records(index, key=self.config.get("records_key"))
        if len(entries) > int(self.config.get("max_batch", 100)):
            raise VendorError("Feed exceeds bounded batch; use an incremental cursor")
        out = []
        for stub in entries:
            number = stub.get("number")
            if number is None:
                raise VendorError("Paperless Parts feed record missing number")
            params = {}
            if entity_type == "quote" and stub.get("revision") is not None:
                params["revision"] = stub["revision"]
            suffix = "?" + urlencode(params) if params else ""
            detail = self._http("GET", f"/{plural}/public/{safe_segment(number)}{suffix}")
            if not isinstance(detail, dict):
                raise VendorError("Expected detail object")
            revision = detail.get("revision_number", stub.get("revision"))
            key = str(number) + (f":{revision}" if revision is not None and entity_type == "quote" else "")
            out.append(ExternalRecord(key, entity_type, detail))
        return out

    def push(self, entity_type, operation, payload):
        # Narrow, documented PATCH actions. Never guess an arbitrary mutable path.
        if not self.config.get("allow_writes"):
            return PushReceipt(False, message="Paperless Parts writes disabled")
        if operation != "update" or entity_type not in {"quote", "order"}:
            return PushReceipt(False, message="Unsupported Paperless Parts write")
        number = payload.get("number")
        if number is None:
            return PushReceipt(False, message="External number required")
        if entity_type == "quote":
            if "status" not in payload or set(payload) - {"number", "status", "revision"}:
                return PushReceipt(False, message="Only documented quote status updates are allowed")
            suffix = "?" + urlencode({"revision": payload["revision"]}) if payload.get("revision") is not None else ""
            self._http("PATCH", f"/quotes/public/{safe_segment(number)}/status_change{suffix}", {"status": payload["status"]})
        else:
            if "erp_code" not in payload or set(payload) != {"number", "erp_code"}:
                return PushReceipt(False, message="Only documented order ERP code updates are allowed")
            self._http("PATCH", f"/orders/public/{safe_segment(number)}", {"erp_code": payload["erp_code"]})
        return PushReceipt(True, str(number), "Paperless Parts accepted request", {"status": "accepted"})


class FulcrumAdapter(VendorHTTP):
    default_base_url = "https://api.fulcrumpro.com"
    # This adapter relies on the configured OpenAPI routes. E.g. sales-orders.
    # It does not silently turn a quote into a Fulcrum order without mapping.
    def __init__(self, config, credentials=None, *, transport=None):
        super().__init__(config, credentials, transport=transport)
        self.config = dict(self.config)
        self.config.setdefault("read_routes", {"sales_order": "/api/sales-orders/{id}"})
        self.config.setdefault("write_routes", {
            "sales_order": {"create": "/api/sales-orders", "update": "/api/sales-orders/{id}"}
        })

    def _base_url(self):
        base = super()._base_url()
        if not (base.endswith(".fulcrumpro.com") or base.endswith(".fulcrumpro.us") or
                base in {"https://api.fulcrumpro.com", "https://api.fulcrumpro.us"}):
            raise VendorError("Fulcrum host must be a verified Fulcrum API domain")
        return base


class PaperlessFulcrumBridge:
    """Explicit, mapped handoff from a Paperless Parts quote to a Fulcrum order.

    Preview and transformation are separate from transmission. A caller supplies
    the destination's validated OpenAPI payload, not an unverified guess.
    """
    def __init__(self, paperless: PaperlessPartsAdapter, fulcrum: FulcrumAdapter):
        self.paperless, self.fulcrum = paperless, fulcrum

    def preview_quote(self, number):
        item = self.paperless.pull("quote", cursor=str(number))[0]
        data = item.payload
        return {
            "source": "paperless_parts",
            "quote_number": str(data.get("number") or number),
            "revision": data.get("revision_number"),
            "status": data.get("status"),
            "requires_destination_mapping": True,
            "source_id": item.external_id,
        }

    def create_fulcrum_order(self, number, *, destination_payload, approved=False):
        preview = self.preview_quote(number)
        if not approved:
            return {"submitted": False, "preview": preview, "reason": "Review and approval required"}
        if not isinstance(destination_payload, dict) or not destination_payload:
            raise ValueError("Validated Fulcrum sales order payload required")
        if destination_payload.get("source_quote_number") != preview["quote_number"]:
            raise ValueError("Source quote identity mismatch")
        # Metadata for audit is not automatically sent to Fulcrum; mapping must
        # produce exactly the accepted vendor schema.
        wire = dict(destination_payload)
        wire.pop("source_quote_number")
        receipt = self.fulcrum.push("sales_order", "create", wire)
        return {"submitted": receipt.ok, "external_id": receipt.external_id,
                "message": receipt.message, "preview": preview}

"""No network, tokens or real business data. Vendor connectors use fictional fixtures."""
import io
import json
from urllib.parse import urlsplit
from urllib.request import Request

import pytest

from superforge.integrations.base import PushReceipt
from superforge.integrations.paperless_fulcrum import (
    FulcrumAdapter, PaperlessFulcrumBridge, PaperlessPartsAdapter,
)
from superforge.integrations.jobboss2_writer import JobBoss2WriteAdapter
from superforge.integrations.vendor_http import MyTrackAdapter, VendorError, records


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Transport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request, timeout):
        assert isinstance(request, Request)
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("Unexpected vendor request")
        return Response(json.dumps(self.replies.pop(0)).encode("utf-8"))


def test_paperless_quote_index_detail_and_revision():
    client = Transport([
        [{"number": 42, "revision": 2}],
        {"number": 42, "revision_number": 2, "status": "sent"},
    ])
    api = PaperlessPartsAdapter({}, {"api_token": "TEST"}, transport=client)
    found = api.pull("quote")
    assert len(found) == 1
    assert found[0].external_id == "42:2"
    assert urlsplit(client.requests[0].full_url).path == "/quotes/public/new"
    assert client.requests[1].full_url.endswith("/quotes/public/42?revision=2")
    assert client.requests[1].get_header("Authorization") == "API-Token TEST"


def test_paperless_status_write_opt_in_only():
    transport = Transport([{}])
    api = PaperlessPartsAdapter({"allow_writes": True}, {"token": "TEST"}, transport=transport)
    result = api.push("quote", "update", {"number": 42, "status": "outstanding"})
    assert result.ok
    assert transport.requests[0].get_method() == "PATCH"
    assert transport.requests[0].full_url.endswith("/quotes/public/42/status_change")
    assert json.loads(transport.requests[0].data) == {"status": "outstanding"}
    assert not api.push("quote", "create", {"number": 42}).ok
    assert not api.push("order", "update", {"number": 5, "unspecified": "value"}).ok


def test_fulcrum_create_and_update_requires_explicit_enable():
    transport = Transport([{"id": "so-test-1"}, {"id": "so-test-1"}])
    api = FulcrumAdapter({"allow_writes": False}, {"token": "TEST"}, transport=transport)
    assert api.push("sales_order", "create", {"customerId": "demo"}).ok is False
    assert transport.requests == []
    api.config["allow_writes"] = True
    assert api.push("sales_order", "create", {"customerId": "demo"}).external_id == "so-test-1"
    assert api.push("sales_order", "update", {"id": "so-test-1", "note": "demo"}).ok
    assert [r.get_method() for r in transport.requests] == ["POST", "PATCH"]
    assert transport.requests[1].full_url.endswith("/api/sales-orders/so-test-1")


def test_jobboss_oauth_and_record_edit():
    transport = Transport([{"access_token": "SHORT-TEST-TOKEN"}, {"orderNumber": "TEST-001"}])
    api = JobBoss2WriteAdapter({"allow_writes": True}, {
        "client_id": "TEST", "client_secret": "TEST"
    }, transport=transport)
    result = api.push("sales_order", "update", {"orderNumber": "TEST-001", "status": "open"})
    assert result.ok
    assert transport.requests[0].get_method() == "POST"
    assert urlsplit(transport.requests[0].full_url).hostname == "api-user.integrations.ecimanufacturing.com"
    assert transport.requests[1].get_method() == "PATCH"
    assert transport.requests[1].full_url.endswith("/api/v1/orders/TEST-001")
    assert transport.requests[1].get_header("Authorization") == "Bearer SHORT-TEST-TOKEN"
    assert not api.push("sales_order", "delete", {"orderNumber": "TEST-001"}).ok


def test_jobboss_write_routes_cover_time_and_customer_records():
    transport = Transport([{"Data": {"timeTicketGUID": "sample-id"}}, {}])
    api = JobBoss2WriteAdapter({"allow_writes": True}, {"token": "TEST"}, transport=transport)
    assert api.pull("time_ticket_detail", cursor="sample-id")[0].external_id == "sample-id"
    result = api.push("customer", "update", {"customerCode": "DEMO", "customerName": "Example Only"})
    assert result.ok
    assert transport.requests[0].full_url.endswith("/api/v1/time-ticket-details/sample-id")
    assert transport.requests[1].full_url.endswith("/api/v1/customers/DEMO")
    assert transport.requests[1].get_method() == "PATCH"


def test_mytrack_requires_real_vendor_interface_and_never_invents_routes():
    transport = Transport([])
    api = MyTrackAdapter({"base_url": "https://api.example.invalid", "allow_writes": True}, {
        "token": "TEST",
    }, transport=transport)
    with pytest.raises(VendorError, match="not verified"):
        api.pull("job")
    api.config["mytrack_interface_verified"] = True
    with pytest.raises(VendorError, match="No configured read route"):
        api.pull("job")
    with pytest.raises(VendorError, match="No configured update route"):
        api.push("job", "update", {"id": "DEMO"})


def test_dry_run_bridge_must_not_submit_and_identity_must_match():
    paperless_transport = Transport([
        {"number": 73, "revision_number": 1, "status": "sent"},
        {"number": 73, "revision_number": 1, "status": "sent"},
        {"number": 73, "revision_number": 1, "status": "sent"},
    ])
    fulcrum_transport = Transport([{"id": "so-73"}])
    bridge = PaperlessFulcrumBridge(
        PaperlessPartsAdapter({}, {"token": "TEST"}, transport=paperless_transport),
        FulcrumAdapter({"allow_writes": True}, {"token": "TEST"}, transport=fulcrum_transport),
    )
    assert not bridge.create_fulcrum_order(73, destination_payload={}, approved=False)["submitted"]
    assert not fulcrum_transport.requests
    with pytest.raises(ValueError, match="mismatch"):
        bridge.create_fulcrum_order(73, destination_payload={"source_quote_number": "no", "customerId": "TEST"}, approved=True)
    assert not fulcrum_transport.requests
    result = bridge.create_fulcrum_order(73, destination_payload={
        "source_quote_number": "73", "customerId": "demo-customer"
    }, approved=True)
    assert result["submitted"]
    posted = json.loads(fulcrum_transport.requests[0].data)
    assert "source_quote_number" not in posted


def test_unknown_collection_does_not_silently_skip_records():
    with pytest.raises(VendorError):
        records({"unexpected": [{"id": "test"}]})


def test_registry_contains_vendor_adapters():
    from superforge.integrations.service import ADAPTERS
    assert {"paperless_parts", "fulcrum", "jobboss2_write", "mytrack"} <= set(ADAPTERS)

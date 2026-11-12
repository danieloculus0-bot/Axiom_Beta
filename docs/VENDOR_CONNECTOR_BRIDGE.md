# Axiom vendor connector bridge (feature branch)

Axiom's existing backend adapter registry and integration outbox now support
independently configured integrations named paperless_parts, fulcrum,
jobboss2_write and mytrack. The first two form one **Paperless Parts / Fulcrum**
quoting-to-shop-floor workflow. Paperless Parts and Fulcrum are separate
products, each with an independent API and credentials.

These are server-side Python adapters, **not** browser or GitHub Pages
connections. No live account, credential, private company data or vendor
authorization is included. Do not assume a configured or operating connection
until tested against the relevant organization's approved environment.

## Supported contracts

| Adapter type | Pull | Outbound write |
| --- | --- | --- |
| paperless_parts | Quote/order detail by number, bounded new quote/order feeds | Documented quote status PATCH, order ERP-code PATCH only |
| fulcrum | Configured REST collection/detail routes, documented sales-order endpoint | Configured create POST and update PATCH/PUT, opt-in |
| jobboss2_write | Configured JobBOSS2 Public API routes | POST/PATCH per configured allowed entity routes, opt-in |
| mytrack | Endpoint mapping required | Endpoint and vendor interface verification required, opt-in |

All four use the existing ERPAdapter/IntegrationService registration and may
use an externally supplied credential_loader. Existing SQL import reconciliation,
external references and outbound outbox must be configured separately. At present
the service's import table mappings do **not** treat an entire quote or sales
order as an Axiom job. Use the adapter's pull and a reviewed field mapping before
any conversion. The module is not an automatic three-system synchronizer.

### Fulcrum and Paperless Parts

Paperless Parts public API documentation:
https://docs.paperlessparts.com/
https://www.paperlessparts.com/api/

Fulcrum developer documentation:
https://developers.fulcrumpro.com/
https://developers.fulcrumpro.com/docs/authentication
Fulcrum and Paperless Parts commercial integration:
https://fulcrumpro.com/integration/paperless-parts

Paperless Parts uses header Authorization: API-Token <token>.
Fulcrum uses header Authorization: Bearer <token>. Fulcrum's ITAR site
uses api.fulcrumpro.us instead of .com.

Example Python preview, not a live integration:

    from superforge.integrations.paperless_fulcrum import (
        PaperlessPartsAdapter, FulcrumAdapter, PaperlessFulcrumBridge
    )
    pp = PaperlessPartsAdapter({}, {"api_token": "<local private token>"})
    fu = FulcrumAdapter({"allow_writes": False}, {"token": "<local private token>"})
    preview = PaperlessFulcrumBridge(pp, fu).preview_quote(123)

The bridge deliberately requires an explicit approved=True flag, a destination
payload validated against the tenant's current Fulcrum OpenAPI schema, and
matching source_quote_number before a Fulcrum order POST. It does not fabricate
BOM, currency, operation, customer, quote acceptance, or routing data.
For tenant implementations, keep quote-to-order mapping, replays and write
authorization in the controlled, non-public environment.

### JobBOSS2 write and edit

An existing EWI reader remains unchanged. The new jobboss2_write adapter
authenticates to the ECI API-user OAuth client-credentials endpoint and uses
the official hosted JobBOSS2 API, **not direct SQL mutation**. Credentials may
come from Axiom's credential loader; AXIOM_JB2_CLIENT_ID and
AXIOM_JB2_CLIENT_SECRET are accepted locally by this adapter for the ECI token.

Example adapter configuration (fictional values, do not commit secrets):

    {
      "adapter_type": "jobboss2_write",
      "enabled": true,
      "credentials_ref": "<local secret-store reference>",
      "config_json": "{\"allow_writes\":true}"
    }

The built-in create/update example targets the published order endpoints.
For other entities, set read_routes, write_routes and id_fields to the
exact ECI OpenAPI contract for the authorized tenant. POST and PATCH are
different from deleting or editing unsupported fields. Reconcile the ECI
response and its effective ERP state before marking business operations done.

### MyTrack

"MyTrack" is not a unique product identifier. The mytrack adapter makes no
claim that any particular MyTrack vendor is the intended system. Obtain the installation's
approved system/vendor, base API URL, entity paths, authentication type,
read/write permission and schema, then configure mytrack_interface_verified,
read_routes and write_routes. Until then, network calls fail closed.

An illustrative local-only configuration shape, **not a vendor endpoint**:

    {
      "base_url": "https://api.example.invalid",
      "mytrack_interface_verified": false,
      "read_routes": {"job": "/EXAMPLE-JOB-ROUTE"},
      "write_routes": {"job": {"update": "/EXAMPLE-JOB-ROUTE/{id}"}},
      "allow_writes": false
    }

Do not change this verification flag to true until the specific endpoint and
authority are independently confirmed.

## Operational boundaries

- Keep all site names, real records, proprietary mappings and secrets off GitHub.
- Verify vendor permissions for each action. A configured endpoint is not a grant.
- Set allow_writes explicitly; false blocks outbound mutations.
- For JobBOSS2, Fulcrum and MyTrack outbound writes, the existing durable
  integration_outbox may queue records and IntegrationService.flush_outbox
  can dispatch them when the connection is enabled. Failed requests should
  be retried only after examining the remote system and idempotence policy;
  no exactly-once delivery is promised.
- Use non-production tenants, synthetic fixtures and approved identities for
  initial tests. No real business write has been executed.
- There is no public UI/API route for configuring tenants. Production use
  requires deployment, credential injection, field mapping and end-to-end tests.

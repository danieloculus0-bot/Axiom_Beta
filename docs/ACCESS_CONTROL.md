# Axiom HTTP access boundary (experimental)

Axiom is not yet certified or ready for unrestricted multiuser shop deployment. This change protects Flask HTTP endpoints, not direct Python calls, local filesystem access, or database writes.

## Default localhost mode

AXIOM_ACCESS_MODE=local (default) accepts only socket peers at loopback addresses (127.0.0.1 and ::1). Keep the server bound to 127.0.0.1. Never put local mode behind a proxy, tunnel or remote gateway that maps external connections to loopback: local mode cannot distinguish them.

## Experimental shared-user mode

Set AXIOM_ACCESS_MODE=shared and AXIOM_USERS_JSON to a private JSON object. Each key is a username, and each value contains a role and a Werkzeug password_hash. Valid roles: admin, quality, operations, finance, viewer. At least one administrator is required. The process refuses to start if the map is missing or invalid.

Generate credentials with local Python: from werkzeug.security import generate_password_hash; print(generate_password_hash("a-long-unique-password"))

Do not commit actual passwords or hashes to repositories. Configure HTTPS directly; shared mode blocks non-TLS requests outside test runs. Session cookies are HttpOnly, Secure and SameSite Strict. Do not expose this experimental mode to the Internet yet: brute force protection, secure reverse proxy integration, account lifecycle and multi-process revocation still require work.

## Roles

- admin: all pages and HTTP mutations.
- quality: ordinary read access, modifications to /quality/* only.
- operations: ordinary read access, modifications to /pm and /clocking-errors.
- finance: payroll/accounting/sheets views and associated dedicated mutations.
- viewer: ordinary read access only.

Sensitive payroll, accounting, executive, leadership and system audit views are restricted. Most report exports are administrator-only, except narrowly allowed finance exports. These rules are coarse-grained, not per-person, per-part, per-job, or per-customer access control.

Every shared-mode browser modification requires an authenticated session, server-side role permission and CSRF token. Server-generated POST forms receive a hidden _csrf_token input. JSON clients send the token using X-CSRF-Token from the axiom-csrf-token meta tag in rendered HTML. The verified session username supersedes form-supplied actor names for HTTP audit records and event ledger entries.

## Verification and limits

Run: python -m pytest -q tests/test_access_control.py, then the full Axiom suite and installers.

Regressions exercise unknown remote peers in local mode, missing shared configuration, anonymous writes, role denial, unauthorized reads, CSRF rejection, forged audit actor rejection and HTTPS transport requirements.

Not implemented by this patch: identity-verified external ERP writes; per-record access; per-department privacy; direct database/library-call enforcement; rate limiting; deployment behind secure proxy; comprehensive backup/restore; real shop deployment and penetration testing. Do not describe those as solved.
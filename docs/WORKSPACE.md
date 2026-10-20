# Axiom Workspace: integrated local launch point

**Stage:** workspace shell and optional process launcher. This is not yet a
single distributable installer containing every companion engine.

## What works in this revision

- Axiom itself contains the existing ERP, quality, documents, EZ Methods,
  maintenance, quoting, reporting and Axiom intelligence routes.
- `/workspace` provides a Gothic Lime starting page for native workspaces,
  independently installed tools and desktop/BEAN adapters.
- `/api/workspace/status` probes fixed loopback addresses without accepting
  user-provided URLs or executable commands. An unexpected response is shown
  as **identity unverified**, not as a connected module.
- `workspace_launcher.py` can start Axiom and selected installed companion
  processes with one command, supervise their exit, and stop the children it
  started. It does not kill pre-existing services.
- Existing tested local data flows remain ForgeVault to EZ-FAIR to Axiom for
  controlled, review-required FAIs, and ForgeVault to EZstimate to Axiom for
  quote proposals. Starting a companion is **not** a data connector.

## Try it

In the Axiom checkout, using a Python 3.12+ environment with the package
and dependencies installed:

```bash
python -m pip install -e ".[dev]"
python workspace_launcher.py --dry-run
python workspace_launcher.py
```

Open **http://127.0.0.1:5060/workspace**.

This initial command starts the existing Axiom application. By default,
**no optional services** start, because a live production/workstation
instance may already own a port, workbook or database.

To use installed siblings, copy `workspace.modules.example.json` to
`workspace.modules.json`, edit `directory`, `command` and `enabled`,
then run:

```bash
python workspace_launcher.py --config workspace.modules.json --dry-run
python workspace_launcher.py --config workspace.modules.json
```

You can also explicitly request all configured source directories with
`--all`, but confirm they use the intended environment and persistent
data paths first. `{python}` means the interpreter running Axiom; change
the command to your app-specific environment executable when necessary.
Configure the companion applications first, including their own package
requirements. Processes that exit after startup are reported.

Port map (loopback checks): Axiom **5060**, ForgeVault **8766**,
EZstimate **8765**, ForgeQC **5080**, EZ Expedite **5050**, PM-Tracker
**5000**. ForgeVault's normal desktop default is also 8765, hence the
explicit `--port 8766` in the example. If an existing instance
already uses a port, the launcher does not start a second instance.

The launcher exposes Axiom on `127.0.0.1`. Individual companion apps
may have other defaults and require their own service-specific
configuration; the example pins ForgeQC to loopback. EZ-FAIR and EZ-FEA
are native desktop interfaces, not fake browser versions of their engines.
BEAN Core and BEAN AI Bridge operate as separately installed integration
libraries and event adapters, not automatically as servers.

## Next actual integration milestones

1. Verify a common installer and dependency inventory for supported
   Windows and Linux machines, including native solver dependencies.
2. Provide app-owned authenticated local APIs or stable task adapters;
   avoid screen scraping and unsynchronized database copies.
3. Implement one context/revision-aware nav model across independently
   running UI surfaces.
4. Persist verified per-module health and integration contract checks.
5. Add role authentication before LAN/shared-workstation mutation access.
6. Validate with real equipment-specific PM data, drawing revisions,
   quoting approval and rollback; test backups and offline recovery.

## Security and verification

The runtime health check is **not a security or identity proof** and is
not a BEAN connection assertion. It only confirms an expected response
from a loopback port. No web request starts, stops or executes commands.
Do not run shop-network public access until authenticating the callers,
authorizing actions, and establishing proper origin and CSRF controls.

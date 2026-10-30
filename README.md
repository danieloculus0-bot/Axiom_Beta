# Axiom

## Try Axiom now

### [▶ LAUNCH THE LIVE AXIOM ERP DEMO](https://danieloculus0-bot.github.io/Axiom_Beta/erp/)

**Start here.** A functional, interactive manufacturing ERP demonstration with connected fictional jobs, materials, purchasing, maintenance, quality, searchable menus, record-aware right-click **Open with**, and browser-local activity history. Try it directly, no installation required.

**[Open the live ERP demo](https://danieloculus0-bot.github.io/Axiom_Beta/erp/)** · [View source and tests](web/erp/) · [Run the local beta](#run-the-actual-local-beta)

The demo uses invented data saved in your browser. It does not connect to a real company, external ERP, BEAN agent, or production server. The local Axiom beta has additional features not exposed in the demo.

---

**One connected workspace for running a manufacturing business.**

Axiom is a **local-first manufacturing operations and ERP application**. It is being built to connect the everyday work of a fabrication or machining shop: jobs, drawings, estimating, production planning, quality, inventory, purchasing, maintenance, and reporting.

Instead of working from disconnected spreadsheets and separate systems that all know a different piece of the same job, Axiom brings the relevant records together in one application.

**In plain English: Axiom is where a shop can see what needs to be made, what it takes to make it, what has happened to it, and what needs attention next.**

> **Project status: Active beta.** There is a working local application and tested integrations, but this is not yet a fully deployed, production-ready ERP. The public browser lab is a small demonstration, not the entire product.

## Why Axiom exists

Manufacturing information tends to get scattered. A quote lives in one file. The drawing lives somewhere else. Inspection results, material orders, maintenance records, and job updates end up in different programs or personal spreadsheets.

That makes routine questions harder than they should be:

- What is the current drawing revision for this job?
- Has the required inspection been completed?
- Do we have the material, or does purchasing need to act?
- What has already been ordered, received, or consumed?
- Which problems are holding up production?
- Where is the evidence behind a job's status or cost?

**Axiom's goal is to answer those questions from connected, understandable records, without making the user become a software engineer.**

## What Axiom covers

| Area | What it means for the person using it |
| --- | --- |
| **Jobs and manufacturing** | Keep job information and associated production records together. |
| **Drawings and documents** | Associate a job with the correct controlled drawing, version, and supporting documents. |
| **Estimating and quoting** | Bring source-backed estimate proposals into a reviewable quoting workflow. |
| **Quality and inspection** | Track quality cases, inspection information, and first article inspection (FAI) evidence. |
| **Methods and planning** | Link manufacturing methods and requirements to relevant jobs and source documents. |
| **Inventory and purchasing** | Track stock, job reservations, material use, purchasing requests, orders, and receiving. |
| **Suppliers and actual costs** | Review supplier quotes, delivery performance, purchase costs, and invoice differences. |
| **Preventive maintenance** | Keep equipment maintenance work in the same operations environment. |
| **Reporting and oversight** | Make connected operational and quality information easier to find and review. |
| **Spreadsheets and familiar tools** | Work toward bringing existing Excel data into controlled records rather than forcing every shop to rebuild its files. |

Some of these areas are more complete than others. The table describes the product's scope, **not a claim that every workflow is finished or production-approved**.

## A simple example: follow one job

Imagine a shop receives a request to manufacture a bracket.

1. **Estimate it.** The quote is prepared using the relevant part and drawing information.
2. **Plan it.** The job is associated with the correct drawing revision, methods, and material requirements.
3. **Get the material.** Inventory and purchasing can show what is available, reserved, ordered, or received.
4. **Inspect it.** Quality and FAI information can be connected to the job, with measurements and approvals handled separately.
5. **Review the full picture.** The **Job Passport** shows records actually linked to that job, instead of forcing someone to hunt through several systems.

That connected job view is the idea behind Axiom. It is not a promise that all five steps currently run automatically or that a proposal is an approved transaction.

## What works in the current beta

The local Python application has a Flask-based interface and a SQLite data store. Its implemented pieces include:

- Workspaces for jobs, quality, methods, documents, maintenance, purchasing, and reporting.
- A **Job Passport** that gathers directly linked job, drawing, FAI, quality, routing, purchase, and material records in one read-only view.
- Tested controlled-document workflows involving **ForgeVault**, **EZ-FAIR**, and **EZstimate**. Imported inspection characteristics and quote proposals remain subject to review.
- Local purchasing tools for stock settings, reservations, consumption, requisition drafts, purchase-order links, and receiving.
- Supplier offer/delivery analysis and invoice-backed purchase-cost reconciliation.
- A saved Favorites menu and registered-workspace navigation endpoints.
- A simplified Sheet Workbench for spreadsheet import, editing, and export. It is **not** yet a full-fidelity replacement for Excel.
- Windows/Linux build and test workflows, with their actual results visible in [GitHub Actions](https://github.com/danieloculus0-bot/Axiom_Beta/actions).

For precise implementation details and current limitations, see the [engineering documents](#documentation-and-technical-details).

## Where BEAN fits

**Axiom is the manufacturing application. [BEAN](https://github.com/danieloculus0-bot/BEAN) is a separate intelligence and learning system.**

The intended relationship is straightforward: Axiom manages operational records and workflows; BEAN can assist with understanding information, navigating the system, evaluating alternatives, and proposing useful next actions.

BEAN does **not** automatically authorize inspections, release quotes, approve purchases, or rewrite business records. The public demonstration does **not** contain a live BEAN agent.

Related tools such as [EZ-FAIR](https://github.com/danieloculus0-bot/EZ-FAIR), EZstimate, ForgeVault, and EZ-FEA have their own code and responsibilities. Tested, explicit integrations can let them cooperate with Axiom without pretending they are one automatically synchronized program. AIscend and the games are independent projects, **not Axiom modules**.

Read the [product boundaries and integration rules](docs/AXIOM_SCOPE.md).

## See it or run it

### Try the browser demonstration

**[Launch the interactive Axiom ERP demo](https://danieloculus0-bot.github.io/Axiom_Beta/erp/)**. This is the primary browser experience, not the legacy lab.

The live demo is an integrated browser-local ERP suite with fictional work orders, material allocation, purchasing and receiving, routed EWI and clocking, maintenance, quality holds, reporting, searchable menus, and contextual right-click navigation. It represents only the features implemented in the Pages demonstration, not the full local Axiom application. All activity stays local to the browser; no employer data, live ERP connector, or live BEAN service is included.

The [original browser lab](https://danieloculus0-bot.github.io/Axiom_Beta/lab/) is legacy reference material, not the main user experience.

### Run the actual local beta

Requirements: **Python 3.12 or later**.

```bash
git clone https://github.com/danieloculus0-bot/Axiom_Beta.git
cd Axiom_Beta
python -m pip install -r requirements.txt
python run.py
```

Then open **http://127.0.0.1:5060** on the computer running Axiom.

This is intended for a local, trusted workstation while the product is in beta. Do not expose it directly to the internet or an unrestricted shop network. See [access controls and current restrictions](docs/ACCESS_CONTROL.md) and the [earlier detailed installation notes](docs/archive/README_2026-10-20_before_refresh.md).

### Run the tests

```bash
python -m pytest -q
node --test web/engine.test.mjs
```

The second command tests the browser lab and requires Node.js (the project uses Node 22 in CI).

## What is still being developed

Axiom is meant to become a practical, connected manufacturing operating environment. Work still includes:

- Hardening authentication, permissions, backups, and shared-user deployment.
- Completing reliable, authenticated integrations with actual shop ERP systems and external services.
- Expanding workbook handling without losing the original Excel file's formatting, formulas, and revision history.
- Validating real-world use with shop data and operators, not only automated tests and fictional examples.
- Making navigation and everyday workflows easy enough to use without training people on the software's internal architecture.

A passing automated test establishes that the tested code path worked under its test conditions. It does **not** prove that a live ERP is connected or a production transaction was approved.

## Documentation and technical details

The engineering material remains available for people who need it, but it is not the first thing a new visitor should have to read.

| Document | What it covers |
| --- | --- |
| [Axiom product scope](docs/AXIOM_SCOPE.md) | What belongs in Axiom and what remains independent |
| [Architecture](docs/ARCHITECTURE.md) | How the application's components and records fit together |
| [Purchasing intelligence](docs/PURCHASING_INTELLIGENCE.md) | Inventory, demand, requisitions, and receiving |
| [Supplier intelligence](docs/SUPPLIER_INTELLIGENCE.md) | Supplier quotes and delivery evidence |
| [Purchase cost reconciliation](docs/PURCHASE_COST_RECONCILIATION.md) | Invoices, PO prices, and actual material costs |
| [Managed workbooks plan](docs/MANAGED_WORKBOOKS_ARCHITECTURE.md) | Real Excel files and controlled business-data imports |
| [Access control](docs/ACCESS_CONTROL.md) | Local access, experimental shared mode, and limitations |
| [Cross-project build readiness](docs/BUILD_READINESS_SWEEP_2026-10-20.md) | Integration evidence and gaps |
| [Previous detailed README (Oct. 26)](docs/archive/README_2026-10-26_before_product_intro.md) | The former technical README preserved verbatim |
| [Earlier setup/history README](docs/archive/README_2026-10-20_before_refresh.md) | Extended installation notes and project history |

**Bottom line:** Axiom is being built to make the business of manufacturing easier to operate. Its complexity should be behind the scenes, not dumped onto the people trying to use it.

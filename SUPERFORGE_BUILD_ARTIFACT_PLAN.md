# SuperForge Build Artifact Plan

Date: 2026-05-14  
Repo role: unofficial build/distribution artifact repo for SuperForge ERP Suite.

## Source versus artifact boundary

- Primary source/integration repo: `danieloculus0-bot/MFGForge`.
- Source/provenance repos: `danieloculus0-bot/ForgeQC`, `danieloculus0-bot/ForgeVault`, and PM Tracking after real-file audit.
- This repo, `SuperForge_Unofficial`, is not the app source of truth.
- Application routes, schemas, templates, module services, and business logic should live in MFGForge, not here.
- This repo should contain only intentional build outputs, release candidates, packaging notes, generated manifests, installer experiments, and compiled/runtime assets that are safe to distribute.

## Compiled libraries/build outputs that belong here

Only intentional artifacts produced from a known MFGForge source commit belong here, for example:

- Windows executable release candidates such as `SuperForge.exe` or `MFGForge.exe` while naming is being finalized.
- PyInstaller/Nuitka output selected for release-candidate evaluation.
- Installer experiment outputs, for example Inno Setup or WiX packages.
- Bundled runtime asset folders required by the executable.
- Release manifests that record source repo, branch, commit SHA, build timestamp, Python version, dependency lock/hash information, and build command.
- Checksums for executables/installers.
- Build logs that contain no secrets, private paths, customer data, or local machine identifiers beyond sanitized build metadata.
- Icons or runtime assets intentionally embedded in release candidates.

## Files that should never be committed here

- Real customer drawings, quote PDFs, RMA/NCR/DMR/CAPA records, certs, inspection results, private documents, or customer/vendor data.
- Runtime SQLite databases such as `mfgforge.sqlite`, `forgeqc.db`, PM databases, or copied customer vault databases.
- Private Excel trackers, imports, exports, attendance/morale files, machine logs, maintenance histories, or company-private reports.
- Secrets, passwords, tokens, `.env` files with real values, API keys, connection strings, or machine-specific config.
- `venv`, `.venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, build scratch folders, temporary extraction folders, or local package caches.
- Unreviewed raw `dist/` or `build/` folders dumped at repo root.
- Source-of-truth application modules copied from MFGForge, ForgeQC, ForgeVault, or PM Tracking.
- Local absolute paths such as `C:\Users\...` embedded in config or manifests unless sanitized examples are clearly marked.

## Expected artifact folder layout

```text
SuperForge_Unofficial/
  SUPERFORGE_BUILD_ARTIFACT_PLAN.md
  release-candidates/
    superforge-erp-YYYY.MM.DD-rcN/
      manifest.json
      checksums.sha256
      README.md
      windows/
        SuperForge.exe
        SuperForge-Setup.exe          # optional installer once available
        runtime-assets/               # optional, only if the executable needs sidecar assets
      logs/
        build.log                     # sanitized only
        smoke-test.log                # sanitized only
  installer-experiments/
    inno-setup/
    wix/
  compiled-libraries/
    README.md                         # describe why each compiled library is present
  packaging-notes/
    decisions.md
```

Root-level artifact dumps should be avoided. Every release candidate should live in a named folder with a manifest and checksum file.

## Packaging workflow from MFGForge source to unofficial build repo

1. **Prepare source in MFGForge.**
   - Work from the approved branch, currently `integration/superforge-suite` for this integration effort.
   - Run source tests and smoke checks in MFGForge.
   - Confirm no private data, local databases, venvs, cache folders, or machine-specific files are staged.

2. **Build in MFGForge.**
   - Use the MFGForge packaging script once the required spec/build files exist and tests pass.
   - The current MFGForge script path is `scripts/build_windows_exe.ps1`.
   - The build should run a launcher health check before and after packaging.

3. **Create a release candidate folder here.**
   - Use the naming convention below.
   - Copy only the intentional executable/installer/runtime sidecar files.
   - Do not copy raw source repos or runtime databases.

4. **Write provenance manifest.**
   - Include MFGForge repo URL, source branch, source commit SHA, build command, build OS, build timestamp, artifact names, checksums, and whether the artifact is a test build or release candidate.
   - Reference ForgeQC/ForgeVault/PM provenance only as source history, not as bundled source code, unless a compiled/library artifact explicitly requires it.

5. **Run artifact smoke checks.**
   - Run the packaged executable health check.
   - Launch locally if needed and verify it uses a local app data database path rather than a committed database.
   - Store sanitized smoke-test output in the release candidate `logs/` folder.

6. **Commit artifact metadata and intentional outputs.**
   - Commit small, meaningful artifact steps.
   - Large binaries should only be committed if intentionally accepted for this unofficial distribution repo.
   - Prefer one release-candidate commit per RC folder.

## Release candidate naming convention

Recommended folder naming:

```text
release-candidates/superforge-erp-YYYY.MM.DD-rcN/
```

Examples:

```text
release-candidates/superforge-erp-2026.05.14-rc1/
release-candidates/superforge-erp-2026.05.14-rc2/
```

Recommended executable/installer naming inside the RC folder:

```text
SuperForge.exe
SuperForge-Setup-YYYY.MM.DD-rcN.exe
```

Manifest fields should include:

```json
{
  "product": "SuperForge ERP Suite",
  "candidate": "superforge-erp-YYYY.MM.DD-rcN",
  "source_repo": "danieloculus0-bot/MFGForge",
  "source_branch": "integration/superforge-suite",
  "source_commit": "<commit-sha>",
  "build_repo": "danieloculus0-bot/SuperForge_Unofficial",
  "build_timestamp_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "build_command": "<sanitized command>",
  "artifact_type": "windows-exe|installer|runtime-assets",
  "human_approval_required": true
}
```

## Windows `.exe` build output expectations

The final local Windows executable should:

- Launch one SuperForge ERP Suite app, not separate ForgeQC/ForgeVault/PM servers.
- Use Flask + SQLite from the MFGForge source tree.
- Store runtime data under a local Windows app data folder, not inside the Git repo.
- Open the local UI automatically or provide a clear desktop window/launcher.
- Pass a packaged health check before being copied here.
- Include no real business data, demo customer records, private drawings, or local databases.
- Preserve human approval gates for BOM review, material assignments, certs, deviations, quotes, shipments, purchasing actions, PM closures, machine readiness, and customer-facing actions.
- Include version/provenance metadata visible to support and traceable back to an MFGForge commit.

## Current status

No executable, installer, compiled library, or release candidate has been built as part of this audit-only step.

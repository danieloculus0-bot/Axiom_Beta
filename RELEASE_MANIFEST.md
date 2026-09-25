# SuperForge Release Manifest

## Current source branch

```text
danieloculus0-bot/MFGForge @ integration/superforge-suite
```

## Build command

From the MFGForge repo root on Windows:

```powershell
.\scripts\verify_runtime.ps1
.\scripts\build_windows_exe.ps1
```

## Expected artifact

```text
dist\SuperForge.exe
```

## Required launch verification

The packaged executable must pass:

```powershell
.\dist\SuperForge.exe --health-check
```

The health check verifies:

- dashboard launches
- Company Pulse launches through the SuperForge wrapper
- Intelligence Hub launches
- workflow pages launch
- AI policy page launches
- critical create forms launch
- material cert, machine utilization, supplier performance, and quote intake routes load

## Artifact handling

When a build is promoted, copy release candidates here with:

- executable
- checksum file
- version manifest
- source commit SHA
- build notes
- launch verification result

Do not add customer data, private drawings, real RMA records, cert files, quote PDFs, attendance data, or private company records.

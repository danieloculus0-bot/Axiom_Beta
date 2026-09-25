# Axiom Beta Release Manifest

## Canonical source

```text
danieloculus0-bot/Axiom_Beta @ main
```

All CI, test, and packaged builds must checkout and build from this repository. The former SuperForge/MFGForge repositories are migration sources and references, not the release root.

## Build

The GitHub Actions workflow `.github/workflows/windows-build.yml` performs:

1. checkout of `Axiom_Beta/main`
2. Python 3.12 setup
3. dependency installation
4. full pytest source suite
5. one-file PyInstaller build
6. frozen executable health smoke test
7. artifact upload

## Expected Windows artifact

```text
dist\Axiom.exe
```

Actions artifact name:

```text
Axiom-Beta-Windows
```

## Runtime verification

The frozen executable must start from the Axiom checkout/build directory and respond successfully at:

```text
http://127.0.0.1:5060/health
```

Expected application identity is `Axiom`.

## Persistent data

Fresh installs use the Axiom data root. Existing SuperForge data/audit storage is detected and preserved for continuity rather than silently creating a disconnected audit history.

## Release evidence

A promoted build should retain:

- source commit SHA
- test result
- Windows build result
- frozen health-check result
- executable artifact
- checksum when a formal release package is created

Do not commit customer data, drawings, live RMA records, payroll exports, attendance records, material certs, quote PDFs, or other private company records.

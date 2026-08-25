# APKForge

**Reverse. Analyze. Transform. Rebuild.**

APKForge is a local cybersecurity research demo tool for working with Android APKs in a controlled environment. It validates an uploaded APK, extracts archive contents, optionally runs established reverse-engineering tools, generates a structured static-analysis report, and exposes a controlled demo modification/rebuild/sign workflow.

This initial version intentionally uses a simple Flask page and modular Python backend.

## What Works

- APK upload and per-run isolated workspaces under `workspace/<run_id>/`
- APK validation using ZIP structure checks
- Safe APK archive extraction
- Optional Apktool decode into resources and Smali, when `apktool` is installed
- Optional JADX decompilation into Java-like reconstructed code, when `jadx` is installed
- JSON static analysis report with DEX files, native libraries, URLs/domains, permissions/components when a decoded manifest is available, and basic security indicators
- Controlled demo modification that adds a harmless marker asset to decoded researcher-owned/demo APKs
- Optional Apktool rebuild and apksigner signing/verification, when Android build tools are installed
- Command logging with exit codes under each run's `logs/workflow.log`

Java-like output is labeled as reconstructed/decompiled code because APK reverse engineering cannot guarantee recovery of original source.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional external tools for the full workflow:

- `apktool`
- `jadx`
- Android SDK build tools with `apksigner`
- JDK `keytool`
- `adb` for future device installation workflows

Without those tools, the demo still validates, extracts, scans, logs skipped tools, and produces a report.

## Run

```bash
flask --app apkforge.app.server run --host 127.0.0.1 --port 5000
```

Open `http://127.0.0.1:5000`, upload an APK, and start analysis. Rebuild/sign controls become available after analysis when decoded Apktool output exists.

## Test

```bash
python -m pytest
```

## Project Layout

```text
apkforge/
├── app/
│   ├── server.py
│   ├── routes.py
│   ├── static/
│   └── templates/
├── core/
│   ├── analyzer.py
│   ├── builder.py
│   ├── decompiler.py
│   ├── extractor.py
│   ├── modifier.py
│   ├── signer.py
│   └── validator.py
├── tools/
│   ├── adb.py
│   ├── apksigner.py
│   ├── apktool.py
│   ├── jadx.py
│   └── runner.py
├── workspace/
├── output/
└── tests/
```

## Research Boundary

The modification layer is deliberately limited to harmless demo behavior. Do not use APKForge to modify third-party applications or add credential theft, OTP interception, spyware, persistence, or data exfiltration behavior.

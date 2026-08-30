# MessAPK

Educational APK reverse-engineering, analysis, editing, and rebuild platform.

MessAPK is a local web app for authorized APK research. It uploads and validates APKs, extracts them, runs Apktool and JADX when available, presents metadata and semantic APK structure, allows controlled edits to decoded text artifacts, tracks diffs, rebuilds with Apktool, aligns, signs, verifies, and exposes downloadable artifacts.

## Current Deliverables

- Upload and validate APK files
- Per-run isolated workspaces under `workspace/<run_id>/`
- APK file metadata: filename, size, SHA-256, DEX count, resources, native libraries, architecture indicators, signing entries
- Apktool decode for manifest/resources/smali when installed
- JADX Java-like reconstructed source when installed
- Clear partial status when external tools are missing
- Metadata dashboard
- Semantic Manifest Explorer
- Interactive APK tree explorer
- Code/file viewer for decoded, decompiled, extracted, analysis, modified, and log artifacts
- Controlled text editing for decoded Apktool files only
- Modification tracking and before/after unified diffs
- Apktool rebuild
- Zipalign step
- Uber APK Signer support, with apksigner fallback
- Signature verification
- Download links for generated artifacts

MessAPK does not claim to recover original source exactly. JADX output is reconstructed Java-like code; Smali and decoded resources remain the rebuild-oriented representation.

## Safety Boundary

Use MessAPK only with APKs you own or are explicitly authorized to modify. The app does not provide malware, hidden backdoor, credential theft, OTP interception, spyware, persistence, or data exfiltration templates.

## Setup

```bash
cd /home/shivangi/projects/APKmess
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
flask --app apkforge.app.server run --host 127.0.0.1 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

## Test

```bash
source .venv/bin/activate
python -m pytest -q
```

## External Tool PATH

Check what is installed:

```bash
for t in apktool jadx zipalign uber-apk-signer apksigner keytool adb; do
  printf '%-16s ' "$t"
  command -v "$t" || echo "not found"
done
```

Minimum useful demo:

- `apktool`
- `jadx`

Full rebuild/sign demo:

- `apktool`
- `zipalign`
- `uber-apk-signer` or `apksigner`
- `keytool`

Android SDK tools are usually added with:

```bash
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/35.0.0:$ANDROID_HOME/cmdline-tools/latest/bin
```

Add those lines to `~/.bashrc` once the SDK is installed.

made with love <3
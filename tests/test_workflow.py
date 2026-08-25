from __future__ import annotations

import json
import zipfile
from pathlib import Path

from apkforge.app.server import create_app
from apkforge.core.validator import validate_apk


def make_demo_apk(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"\x03\x00binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\x00https://demo.example.com Ldalvik/system/DexClassLoader;")
        archive.writestr("lib/arm64-v8a/libdemo.so", b"demo")
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")


def test_validate_apk_accepts_zip_with_manifest_and_dex(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    make_demo_apk(apk)

    result = validate_apk(apk)

    assert result.valid
    assert result.errors == []


def test_flask_analysis_run_creates_report(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    make_demo_apk(apk)
    app = create_app()
    app.config.update(TESTING=True, APKFORGE_WORKSPACE=tmp_path / "workspace", APKFORGE_OUTPUT=tmp_path / "output")

    with app.test_client() as client, apk.open("rb") as handle:
        response = client.post("/api/runs", data={"apk": (handle, "demo.apk")}, content_type="multipart/form-data")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "analyzed"
    assert payload["report"]["dex_files"] == ["classes.dex"]
    assert "report" in payload["artifacts"]

    report_path = tmp_path / "workspace" / payload["run_id"] / "analysis" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "https://demo.example.com" in report["urls"]


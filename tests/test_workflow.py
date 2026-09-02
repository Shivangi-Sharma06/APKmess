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
    assert payload["status"] in {"analyzed", "analyzed_partial"}
    assert payload["report"]["dex_files"] == ["classes.dex"]
    assert "report" in payload["artifacts"]

    report_path = tmp_path / "workspace" / payload["run_id"] / "analysis" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "https://demo.example.com" in report["urls"]


def test_tree_file_and_edit_apis_track_safe_diffs(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    make_demo_apk(apk)
    app = create_app()
    app.config.update(TESTING=True, APKFORGE_WORKSPACE=tmp_path / "workspace", APKFORGE_OUTPUT=tmp_path / "output")

    with app.test_client() as client, apk.open("rb") as handle:
        upload = client.post("/api/runs", data={"apk": (handle, "demo.apk")}, content_type="multipart/form-data")
        run_id = upload.get_json()["run_id"]
        decoded = tmp_path / "workspace" / run_id / "decoded"
        decoded.mkdir(parents=True, exist_ok=True)
        manifest = decoded / "AndroidManifest.xml"
        manifest.write_text("<manifest package=\"demo\" />\n", encoding="utf-8")

        tree = client.get(f"/api/runs/{run_id}/tree")
        assert tree.status_code == 200
        labels = json.dumps(tree.get_json()["tree"])
        assert "Manifest" in labels
        assert "AndroidManifest.xml" in labels

        file_response = client.get(f"/api/runs/{run_id}/file?path=decoded/AndroidManifest.xml")
        assert file_response.status_code == 200
        assert file_response.get_json()["editable"] is True

        blocked = client.get(f"/api/runs/{run_id}/file?path=decoded/../original.apk")
        assert blocked.status_code == 400

        save = client.post(
            f"/api/runs/{run_id}/file",
            json={"path": "decoded/AndroidManifest.xml", "content": "<manifest package=\"changed\" />\n"},
        )
        assert save.status_code == 200
        assert save.get_json()["status"] == "edited"

        diff = client.get(f"/api/runs/{run_id}/diff")
        assert diff.status_code == 200
        assert "changed" in diff.text


def test_ai_edit_requires_visible_proposal_and_approval(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    make_demo_apk(apk)
    app = create_app()
    app.config.update(TESTING=True, APKFORGE_WORKSPACE=tmp_path / "workspace", APKFORGE_OUTPUT=tmp_path / "output")

    with app.test_client() as client, apk.open("rb") as handle:
        upload = client.post("/api/runs", data={"apk": (handle, "demo.apk")}, content_type="multipart/form-data")
        run_id = upload.get_json()["run_id"]
        decoded = tmp_path / "workspace" / run_id / "decoded"
        decoded.mkdir(parents=True, exist_ok=True)
        manifest = decoded / "AndroidManifest.xml"
        manifest.write_text("<manifest><application android:label=\"Old\" /></manifest>\n", encoding="utf-8")

        proposal = client.post(
            f"/api/runs/{run_id}/ai/propose",
            json={"request": "Change the application name to Test Lab"},
        )
        assert proposal.status_code == 200
        proposal_json = proposal.get_json()
        assert proposal_json["requires_approval"] is True
        assert "after_content" not in proposal_json["changes"][0]
        assert "Test Lab" in proposal_json["changes"][0]["diff"]

        blocked = client.post(f"/api/runs/{run_id}/ai/apply", json={"approved": False})
        assert blocked.status_code == 400

        applied = client.post(f"/api/runs/{run_id}/ai/apply", json={"approved": True})
        assert applied.status_code == 200
        modified_manifest = tmp_path / "workspace" / run_id / "modified" / "AndroidManifest.xml"
        assert "Test Lab" in modified_manifest.read_text(encoding="utf-8")
        assert applied.get_json()["metadata"]["modifications"][0]["source"] == "ai"


def test_test_lab_reports_isolated_runtime_boundary(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    make_demo_apk(apk)
    app = create_app()
    app.config.update(TESTING=True, APKFORGE_WORKSPACE=tmp_path / "workspace", APKFORGE_OUTPUT=tmp_path / "output")

    with app.test_client() as client, apk.open("rb") as handle:
        upload = client.post("/api/runs", data={"apk": (handle, "demo.apk")}, content_type="multipart/form-data")
        run_id = upload.get_json()["run_id"]

        status = client.get(f"/api/runs/{run_id}/test-lab")
        assert status.status_code == 200
        status_json = status.get_json()
        assert status_json["capabilities"]["available"] is True
        assert status_json["capabilities"]["isolated_backend_configured"] is True

        launch = client.post(f"/api/runs/{run_id}/test-lab/launch")
        assert launch.status_code == 200
        launch_json = launch.get_json()
        assert launch_json["label"] == "Temporary Test Build"
        assert "isolated" in launch_json["security"][0].lower()


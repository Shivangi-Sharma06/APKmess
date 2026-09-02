from __future__ import annotations

import json
import zipfile
from pathlib import Path

from apkforge.app.server import create_app


def make_sample_apk(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"\x03\x00binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\x00sample-class-data")
        archive.writestr("res/values/strings.xml", "<resources><string name=\"app_name\">SampleApp</string></resources>")
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")


def test_full_end_to_end_smoke_workflow(tmp_path: Path) -> None:
    apk = tmp_path / "sample.apk"
    make_sample_apk(apk)

    app = create_app()
    app.config.update(
        TESTING=True,
        APKFORGE_WORKSPACE=tmp_path / "workspace",
        APKFORGE_OUTPUT=tmp_path / "output",
    )

    with app.test_client() as client, apk.open("rb") as handle:
        # Step 1: Upload APK and Parse Tree
        upload_resp = client.post("/api/runs", data={"apk": (handle, "sample.apk")}, content_type="multipart/form-data")
        assert upload_resp.status_code == 200
        run_data = upload_resp.get_json()
        run_id = run_data["run_id"]
        assert run_id is not None

        # Verify tree endpoint
        tree_resp = client.get(f"/api/runs/{run_id}/tree")
        assert tree_resp.status_code == 200
        tree_nodes = tree_resp.get_json()["tree"]
        assert len(tree_nodes) > 0

        # Step 2: Reverse Engineering / Decompile Check
        decoded_dir = tmp_path / "workspace" / run_id / "decoded"
        decoded_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = decoded_dir / "AndroidManifest.xml"
        manifest_file.write_text('<manifest package="com.example.sample"><application android:label="SampleApp"/></manifest>\n', encoding="utf-8")
        strings_file = decoded_dir / "res" / "values" / "strings.xml"
        strings_file.parent.mkdir(parents=True, exist_ok=True)
        strings_file.write_text('<resources><string name="app_name">SampleApp</string></resources>\n', encoding="utf-8")

        # Step 3: AI Prompt Code Modification
        ai_propose_resp = client.post(
            f"/api/runs/{run_id}/ai/propose",
            json={"request": "Change application name to 'Modified Super App'"},
        )
        assert ai_propose_resp.status_code == 200
        proposal = ai_propose_resp.get_json()
        assert proposal["ok"] is True
        assert len(proposal["changes"]) > 0

        # Apply AI change
        ai_apply_resp = client.post(f"/api/runs/{run_id}/ai/apply", json={"approved": True})
        assert ai_apply_resp.status_code == 200
        assert ai_apply_resp.get_json()["ok"] is True

        # Verify modified workspace
        modified_manifest = tmp_path / "workspace" / run_id / "modified" / "AndroidManifest.xml"
        assert modified_manifest.exists()
        assert "Modified Super App" in modified_manifest.read_text(encoding="utf-8")

        # Step 4: Isolated Environment Test Lab
        test_build_resp = client.post(f"/api/runs/{run_id}/test-lab/build")
        assert test_build_resp.status_code == 200

        launch_resp = client.post(f"/api/runs/{run_id}/test-lab/launch")
        assert launch_resp.status_code == 200
        assert launch_resp.get_json()["ok"] is True

        screenshot_resp = client.post(f"/api/runs/{run_id}/test-lab/screenshot")
        assert screenshot_resp.status_code == 200

        # Step 5: Rebuild, Align, Sign & Download Artifacts
        rebuild_resp = client.post(f"/api/runs/{run_id}/modify-rebuild-sign")
        assert rebuild_resp.status_code == 200
        rebuild_data = rebuild_resp.get_json()
        assert rebuild_data["ok"] is True
        assert rebuild_data["status"] == "signed"
        assert "signed" in rebuild_data["artifacts"]

        # Verify artifact download
        download_resp = client.get(rebuild_data["artifacts"]["signed"])
        assert download_resp.status_code == 200

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from apkforge.core.analyzer import analyze_apk
from apkforge.core.builder import rebuild
from apkforge.core.decompiler import decode_with_apktool, decompile_with_jadx
from apkforge.core.extractor import extract_zip
from apkforge.core.modifier import apply_demo_modification
from apkforge.core.signer import sign_apk, verify_signature
from apkforge.core.validator import validate_apk

bp = Blueprint("apkforge", __name__)


@bp.get("/")
def index() -> str:
    return render_template("index.html")


@bp.post("/api/runs")
def create_run() -> Response:
    upload = request.files.get("apk")
    if not upload or not upload.filename:
        return jsonify({"error": "Upload an APK file first."}), 400
    if not upload.filename.lower().endswith(".apk"):
        return jsonify({"error": "Only .apk files are accepted."}), 400

    run_id = uuid.uuid4().hex[:12]
    run_dir = _run_dir(run_id)
    paths = _paths(run_dir)
    for path in paths.values():
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)

    original_name = secure_filename(upload.filename) or "original.apk"
    apk_path = paths["original"]
    upload.save(apk_path)
    _write_json(paths["metadata"], {"run_id": run_id, "original_filename": original_name, "status": "uploaded"})

    status = _analyze(run_id)
    return jsonify(status), (200 if status.get("ok") else 400)


@bp.post("/api/runs/<run_id>/modify-rebuild-sign")
def modify_rebuild_sign(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return jsonify({"error": "Run not found."}), 404
    result = _modify_rebuild_sign(run_id)
    return jsonify(result), (200 if result.get("ok") else 400)


@bp.get("/api/runs/<run_id>")
def get_run(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return jsonify({"error": "Run not found."}), 404
    return jsonify(_status(run_id))


@bp.get("/api/runs/<run_id>/logs")
def get_logs(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return Response("Invalid run id.", status=400, mimetype="text/plain")
    log_file = _paths(_run_dir(run_id))["workflow_log"]
    return Response(log_file.read_text(encoding="utf-8") if log_file.exists() else "", mimetype="text/plain")


@bp.get("/api/runs/<run_id>/artifacts/<artifact>")
def get_artifact(run_id: str, artifact: str):
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    artifacts = {
        "original": paths["original"],
        "report": paths["report"],
        "unsigned": paths["unsigned_apk"],
        "signed": paths["signed_apk"],
        "workflow-log": paths["workflow_log"],
    }
    target = artifacts.get(artifact)
    if not target or not target.exists():
        return jsonify({"error": "Artifact not found."}), 404
    return send_file(target, as_attachment=True)


def _analyze(run_id: str) -> dict:
    paths = _paths(_run_dir(run_id))
    _log(paths["workflow_log"], f"Run {run_id}: analysis started")
    validation = validate_apk(paths["original"])
    if not validation.valid:
        _log(paths["workflow_log"], "Validation failed: " + "; ".join(validation.errors))
        _write_json(paths["metadata"], {"run_id": run_id, "status": "failed", "errors": validation.errors})
        return _status(run_id) | {"ok": False}
    for warning in validation.warnings:
        _log(paths["workflow_log"], "Validation warning: " + warning)

    extracted = extract_zip(paths["original"], paths["extracted"])
    _log(paths["workflow_log"], f"Extracted {len(extracted)} archive entries")

    apktool_result = decode_with_apktool(paths["original"], paths["decoded"], paths["workflow_log"])
    jadx_result = decompile_with_jadx(paths["original"], paths["decompiled"], paths["workflow_log"])
    report = analyze_apk(paths["original"], paths["extracted"], paths["decoded"], paths["analysis"])
    _write_json(
        paths["metadata"],
        {
            "run_id": run_id,
            "status": "analyzed",
            "validation_warnings": validation.warnings,
            "apktool": _command_dict(apktool_result),
            "jadx": _command_dict(jadx_result),
        },
    )
    _log(paths["workflow_log"], f"Analysis complete: {len(report['security_findings'])} finding(s)")
    return _status(run_id) | {"ok": True}


def _modify_rebuild_sign(run_id: str) -> dict:
    paths = _paths(_run_dir(run_id))
    metadata = _read_json(paths["metadata"])
    _log(paths["workflow_log"], f"Run {run_id}: controlled modification started")
    modification = apply_demo_modification(paths["decoded"], paths["modified"], paths["workflow_log"])
    if not modification.get("applied"):
        metadata["status"] = "modify_failed"
        metadata["modification"] = modification
        _write_json(paths["metadata"], metadata)
        return _status(run_id) | {"ok": False}

    build_result = rebuild(paths["modified"], paths["unsigned_apk"], paths["workflow_log"])
    if not build_result.ok:
        metadata["status"] = "build_failed"
        metadata["modification"] = modification
        metadata["build"] = _command_dict(build_result)
        _write_json(paths["metadata"], metadata)
        return _status(run_id) | {"ok": False}

    keystore = current_app.config["APKFORGE_OUTPUT"] / "apkforge-demo.keystore"
    sign_result = sign_apk(paths["unsigned_apk"], paths["signed_apk"], keystore, paths["workflow_log"])
    verify_result = verify_signature(paths["signed_apk"], paths["workflow_log"]) if sign_result.ok else None

    metadata.update(
        {
            "status": "signed" if sign_result.ok and verify_result and verify_result.ok else "sign_failed",
            "modification": modification,
            "build": _command_dict(build_result),
            "sign": _command_dict(sign_result),
            "verify": _command_dict(verify_result) if verify_result else None,
        }
    )
    _write_json(paths["metadata"], metadata)
    return _status(run_id) | {"ok": metadata["status"] == "signed"}


def _status(run_id: str) -> dict:
    paths = _paths(_run_dir(run_id))
    metadata = _read_json(paths["metadata"])
    report = _read_json(paths["report"])
    artifacts = {}
    for name, path in {
        "original": paths["original"],
        "report": paths["report"],
        "unsigned": paths["unsigned_apk"],
        "signed": paths["signed_apk"],
        "workflow-log": paths["workflow_log"],
    }.items():
        if path.exists():
            artifacts[name] = f"/api/runs/{run_id}/artifacts/{name}"
    return {
        "run_id": run_id,
        "status": metadata.get("status", "unknown"),
        "metadata": metadata,
        "report": report,
        "artifacts": artifacts,
    }


def _paths(run_dir: Path) -> dict[str, Path]:
    return {
        "run": run_dir,
        "original": run_dir / "original.apk",
        "extracted": run_dir / "extracted",
        "decoded": run_dir / "decoded",
        "decompiled": run_dir / "decompiled",
        "analysis": run_dir / "analysis",
        "modified": run_dir / "modified",
        "rebuilt": run_dir / "rebuilt",
        "logs": run_dir / "logs",
        "metadata": run_dir / "analysis" / "metadata.json",
        "report": run_dir / "analysis" / "report.json",
        "workflow_log": run_dir / "logs" / "workflow.log",
        "unsigned_apk": run_dir / "rebuilt" / "modified-unsigned.apk",
        "signed_apk": run_dir / "rebuilt" / "modified-signed.apk",
    }


def _run_dir(run_id: str) -> Path:
    return current_app.config["APKFORGE_WORKSPACE"] / run_id


def _valid_run_id(run_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{12}", run_id))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def _command_dict(result) -> dict | None:
    if result is None:
        return None
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "skipped": result.skipped,
        "reason": result.reason,
        "ok": result.ok,
    }

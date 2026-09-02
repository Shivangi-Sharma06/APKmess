from __future__ import annotations

import json
import re
import uuid
import difflib
import shutil
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from apkforge.core.analyzer import analyze_apk
from apkforge.core.ai_assistant import apply_proposal, implemented_tools, inspect_workspace, propose_authorized_change, public_proposal, search_artifacts
from apkforge.core.builder import align_apk, rebuild
from apkforge.core.decompiler import decode_with_apktool, decompile_with_jadx
from apkforge.core.extractor import extract_zip
from apkforge.core.modifier import apply_demo_modification
from apkforge.core.runtime_lab import build_temporary_test_apk, command_dict as runtime_command_dict, emulator_action, runtime_capabilities, runtime_observations
from apkforge.core.signer import sign_apk, sign_with_uber_apk_signer, verify_signature
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
    for name, path in paths.items():
        if name == "modified":
            continue
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
        "test-signed": paths["test_signed_apk"],
        "workflow-log": paths["workflow_log"],
    }
    target = artifacts.get(artifact)
    if not target or not target.exists():
        return jsonify({"error": "Artifact not found."}), 404
    return send_file(target, as_attachment=True)


@bp.get("/api/runs/<run_id>/tree")
def get_tree(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return jsonify({"error": "Run not found."}), 404
    return jsonify({"tree": _semantic_tree(run_id)})


@bp.get("/api/runs/<run_id>/file")
def get_file(run_id: str) -> Response:
    resolved = _resolve_view_path(run_id, request.args.get("path", ""))
    if _is_error_result(resolved):
        return jsonify({"error": resolved[0]}), resolved[1]
    path, rel = resolved
    if not path.is_file():
        return jsonify({"error": "File not found."}), 404
    if path.stat().st_size > 1_000_000:
        return jsonify({"error": "File is too large for the inline viewer.", "size": path.stat().st_size}), 413
    try:
        content = path.read_text(encoding="utf-8")
        binary = False
    except UnicodeDecodeError:
        content = path.read_bytes()[:512].hex(" ")
        binary = True
    return jsonify({"path": rel, "content": content, "binary": binary, "editable": _editable_path(rel, binary)})


@bp.post("/api/runs/<run_id>/file")
def save_file(run_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    rel_path = payload.get("path", "")
    content = payload.get("content", "")
    if not isinstance(content, str):
        return jsonify({"error": "Content must be text."}), 400
    resolved = _resolve_view_path(run_id, rel_path)
    if _is_error_result(resolved):
        return jsonify({"error": resolved[0]}), resolved[1]
    source_path, rel = resolved
    if not _editable_path(rel, False):
        return jsonify({"error": "This file type is not editable in the demo."}), 400

    paths = _paths(_run_dir(run_id))
    if not paths["modified"].exists() or not any(paths["modified"].iterdir()):
        if not paths["decoded"].exists():
            return jsonify({"error": "Decoded Apktool output is required before editing."}), 400
        if paths["modified"].exists():
            shutil.rmtree(paths["modified"])
        shutil.copytree(paths["decoded"], paths["modified"])

    target = paths["modified"] / Path(rel).relative_to("decoded")
    if not _is_within(paths["modified"], target):
        return jsonify({"error": "Unsafe edit path."}), 400
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            content.splitlines(),
            fromfile=f"before/{rel}",
            tofile=f"after/{rel}",
            lineterm="",
        )
    )
    _record_modification(paths["metadata"], rel, diff)
    _log(paths["workflow_log"], f"Edited {rel}")
    return jsonify(_status(run_id) | {"diff": diff, "ok": True})


@bp.get("/api/runs/<run_id>/diff")
def get_diff(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return Response("Invalid run id.", status=400, mimetype="text/plain")
    metadata = _read_json(_paths(_run_dir(run_id))["metadata"])
    diffs = [item.get("diff", "") for item in metadata.get("modifications", []) if item.get("diff")]
    return Response("\n\n".join(diffs), mimetype="text/plain")


@bp.get("/api/runs/<run_id>/ai/tools")
def get_ai_tools(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    return jsonify({"tools": implemented_tools(), "runtime": runtime_capabilities()})


@bp.get("/api/runs/<run_id>/ai/context")
def ai_context(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    return jsonify(inspect_workspace(paths, _read_json(paths["report"]), request.args.get("q", "")))


@bp.get("/api/runs/<run_id>/ai/search")
def ai_search(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Search query is required."}), 400
    roots = [
        ("decoded", paths["modified"] if paths["modified"].exists() else paths["decoded"]),
        ("decompiled", paths["decompiled"]),
        ("analysis", paths["analysis"]),
        ("logs", paths["logs"]),
    ]
    return jsonify({"results": search_artifacts(query, roots)})


@bp.post("/api/runs/<run_id>/ai/propose")
def ai_propose(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    payload = request.get_json(silent=True) or {}
    proposal = propose_authorized_change(str(payload.get("request", "")), paths, _read_json(paths["report"]))
    if proposal.get("ok") and proposal.get("changes"):
        metadata = _read_json(paths["metadata"])
        metadata["pending_ai_proposal"] = proposal
        metadata["status"] = "ai_proposed"
        _write_json(paths["metadata"], metadata)
        _log(paths["workflow_log"], f"AI proposed {len(proposal.get('changes', []))} change(s); awaiting approval")
    return jsonify(public_proposal(proposal)), (200 if proposal.get("ok") else 400)


@bp.post("/api/runs/<run_id>/ai/apply")
def ai_apply(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    payload = request.get_json(silent=True) or {}
    if payload.get("approved") is not True:
        return jsonify({"error": "Explicit approval is required before AI changes are applied."}), 400
    metadata = _read_json(paths["metadata"])
    proposal = metadata.get("pending_ai_proposal")
    if not proposal:
        return jsonify({"error": "No pending AI proposal to apply."}), 400
    result = apply_proposal(proposal, paths)
    if not result.get("ok"):
        return jsonify(result), 400
    for change in proposal.get("changes", []):
        _record_modification(paths["metadata"], change.get("path", ""), change.get("diff", ""), source="ai")
    metadata = _read_json(paths["metadata"])
    metadata.pop("pending_ai_proposal", None)
    metadata["ai_last_applied"] = public_proposal(proposal)
    metadata["status"] = "edited"
    _write_json(paths["metadata"], metadata)
    _log(paths["workflow_log"], "AI approved changes applied: " + ", ".join(result.get("applied", [])))
    return jsonify(_status(run_id) | {"ok": True, "applied": result.get("applied", [])})


@bp.get("/api/runs/<run_id>/test-lab")
def test_lab_status(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    return jsonify(
        {
            "capabilities": runtime_capabilities(),
            "observations": runtime_observations(paths),
            "has_temporary_test_build": paths["test_signed_apk"].exists(),
            "temporary_test_build": f"/api/runs/{run_id}/artifacts/test-signed" if paths["test_signed_apk"].exists() else None,
        }
    )


@bp.post("/api/runs/<run_id>/test-lab/build")
def test_lab_build(run_id: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    _log(paths["workflow_log"], "Temporary Test Build started")
    result = build_temporary_test_apk(paths, current_app.config["APKFORGE_OUTPUT"], paths["workflow_log"])
    metadata = _read_json(paths["metadata"])
    metadata["test_lab"] = {
        "label": result.get("label"),
        "status": result.get("status"),
        "build": runtime_command_dict(result.get("build")),
        "align": runtime_command_dict(result.get("align")),
        "sign": runtime_command_dict(result.get("sign")),
        "verify": runtime_command_dict(result.get("verify")),
    }
    if result.get("ok"):
        metadata["status"] = "test_signed"
    _write_json(paths["metadata"], metadata)
    return jsonify(_status(run_id) | {"ok": result.get("ok"), "test_lab": metadata["test_lab"]}), (200 if result.get("ok") else 400)


@bp.post("/api/runs/<run_id>/test-lab/<action>")
def test_lab_action(run_id: str, action: str) -> Response:
    if not _valid_run_id(run_id):
        return jsonify({"error": "Invalid run id."}), 400
    if action not in {"launch", "restart-emulator", "reset-app", "clear-data", "stop-app", "reinstall", "screenshot"}:
        return jsonify({"error": "Unsupported Test Lab action."}), 404
    paths = _paths(_run_dir(run_id))
    if not paths["run"].exists():
        return jsonify({"error": "Run not found."}), 404
    result = emulator_action(action, paths)
    _log(paths["workflow_log"], f"Test Lab action '{action}' executed in isolated web container environment.")
    return jsonify(result), 200



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
    analysis_status = "analyzed" if apktool_result.ok and jadx_result.ok else "analyzed_partial"
    _write_json(
        paths["metadata"],
        {
            "run_id": run_id,
            "status": analysis_status,
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
    if not paths["modified"].exists() or not any(paths["modified"].iterdir()):
        modification = apply_demo_modification(paths["decoded"], paths["modified"], paths["workflow_log"])
        if not modification.get("applied"):
            metadata["status"] = "modify_failed"
            metadata["modification"] = modification
            _write_json(paths["metadata"], metadata)
            return _status(run_id) | {"ok": False}
    else:
        modification = {"applied": True, "plugin": "user_edits", "reason": "Using tracked editor modifications."}

    build_result = rebuild(paths["modified"], paths["unsigned_apk"], paths["workflow_log"])
    if not build_result.ok:
        metadata["status"] = "build_failed"
        metadata["modification"] = modification
        metadata["build"] = _command_dict(build_result)
        _write_json(paths["metadata"], metadata)
        return _status(run_id) | {"ok": False}

    align_result = align_apk(paths["unsigned_apk"], paths["aligned_apk"], paths["workflow_log"])
    apk_to_sign = paths["aligned_apk"] if align_result.ok else paths["unsigned_apk"]
    uber_result = sign_with_uber_apk_signer(
        apk_to_sign,
        paths["rebuilt"],
        current_app.config["APKFORGE_OUTPUT"] / "uber-apk-signer.jar",
        paths["workflow_log"],
    )
    sign_result = uber_result
    if uber_result.ok:
        candidate = _find_uber_signed_apk(paths["rebuilt"], apk_to_sign)
        if candidate:
            shutil.copyfile(candidate, paths["signed_apk"])
    else:
        keystore = current_app.config["APKFORGE_OUTPUT"] / "apkforge-demo.keystore"
        sign_result = sign_apk(apk_to_sign, paths["signed_apk"], keystore, paths["workflow_log"])
    verify_result = verify_signature(paths["signed_apk"], paths["workflow_log"]) if sign_result.ok and paths["signed_apk"].exists() else None

    metadata.update(
        {
            "status": "signed" if sign_result.ok and verify_result and verify_result.ok else "sign_failed",
            "modification": modification,
            "build": _command_dict(build_result),
            "align": _command_dict(align_result),
            "uber_apk_signer": _command_dict(uber_result),
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
        "test-signed": paths["test_signed_apk"],
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
        "aligned_apk": run_dir / "rebuilt" / "modified-aligned.apk",
        "signed_apk": run_dir / "rebuilt" / "modified-signed.apk",
        "test_unsigned_apk": run_dir / "test_lab" / "temporary-test-unsigned.apk",
        "test_aligned_apk": run_dir / "test_lab" / "temporary-test-aligned.apk",
        "test_signed_apk": run_dir / "test_lab" / "temporary-test-signed.apk",
        "runtime_log": run_dir / "test_lab" / "runtime-observations.log",
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


def _semantic_tree(run_id: str) -> list[dict]:
    paths = _paths(_run_dir(run_id))
    report = _read_json(paths["report"])
    tree = [
        {"label": "APK Metadata", "kind": "metadata", "children": _metadata_nodes(report)},
        {"label": "Manifest", "kind": "manifest", "path": "decoded/AndroidManifest.xml", "children": _manifest_nodes(report)},
        {"label": "Java-like reconstructed source", "kind": "jadx", "children": _file_nodes(paths["decompiled"], "decompiled")},
        {"label": "Smali and decoded resources", "kind": "apktool", "children": _file_nodes(paths["decoded"], "decoded")},
        {"label": "Modified workspace", "kind": "modified", "children": _file_nodes(paths["modified"], "modified")},
        {"label": "Raw extracted APK", "kind": "archive", "children": _file_nodes(paths["extracted"], "extracted")},
        {"label": "Analysis", "kind": "analysis", "children": _file_nodes(paths["analysis"], "analysis")},
    ]
    return tree


def _metadata_nodes(report: dict) -> list[dict]:
    keys = ["apk_filename", "apk_size", "sha256", "package", "application_name", "version_name", "version_code"]
    return [{"label": f"{key}: {report.get(key) or '-'}", "kind": "metadata"} for key in keys]


def _manifest_nodes(report: dict) -> list[dict]:
    components = report.get("components", {})
    return [
        {"label": f"Permissions ({len(report.get('permissions', []))})", "kind": "permissions", "children": [{"label": p, "kind": "permission"} for p in report.get("permissions", [])]},
        {"label": f"Activities ({len(components.get('activities', []))})", "kind": "activities", "children": _component_nodes(components.get("activities", []))},
        {"label": f"Services ({len(components.get('services', []))})", "kind": "services", "children": _component_nodes(components.get("services", []))},
        {"label": f"Receivers ({len(components.get('receivers', []))})", "kind": "receivers", "children": _component_nodes(components.get("receivers", []))},
        {"label": f"Providers ({len(components.get('providers', []))})", "kind": "providers", "children": _component_nodes(components.get("providers", []))},
        {"label": f"Intent filters ({len(report.get('intent_filters', []))})", "kind": "intent_filters"},
    ]


def _component_nodes(components: list[dict]) -> list[dict]:
    return [{"label": f"{item.get('name') or '<unnamed>'} exported={item.get('exported') or 'unspecified'}", "kind": item.get("type", "component")} for item in components]


def _file_nodes(root: Path, prefix: str, limit: int = 600) -> list[dict]:
    if not root.exists():
        return [{"label": "Unavailable", "kind": "missing"}]
    count = 0

    def build(path: Path) -> dict:
        nonlocal count
        rel = f"{prefix}/{path.relative_to(root).as_posix()}" if path != root else prefix
        node = {"label": path.name or prefix, "kind": "directory" if path.is_dir() else "file", "path": rel}
        if path.is_dir() and count < limit:
            children = []
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                count += 1
                if count > limit:
                    children.append({"label": "Tree truncated", "kind": "truncated"})
                    break
                children.append(build(child))
            node["children"] = children
        return node

    return build(root).get("children", [])


def _resolve_view_path(run_id: str, rel_path: str):
    if not _valid_run_id(run_id):
        return ("Invalid run id.", 400)
    paths = _paths(_run_dir(run_id))
    allowed = {name: paths[name] for name in ["decoded", "decompiled", "extracted", "analysis", "modified", "logs"]}
    rel = Path(rel_path)
    if not rel.parts or rel.parts[0] not in allowed:
        return ("Path must start with decoded, decompiled, extracted, analysis, modified, or logs.", 400)
    base = allowed[rel.parts[0]]
    target = base.joinpath(*rel.parts[1:])
    if not _is_within(base, target):
        return ("Unsafe path.", 400)
    return target, rel.as_posix()


def _is_error_result(result) -> bool:
    return isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], str) and isinstance(result[1], int)


def _editable_path(rel: str, binary: bool) -> bool:
    if binary or not rel.startswith("decoded/"):
        return False
    return Path(rel).suffix.lower() in {".xml", ".smali", ".json", ".txt", ".properties", ".yml", ".yaml"}


def _is_within(parent: Path, child: Path) -> bool:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    return parent_resolved == child_resolved or parent_resolved in child_resolved.parents


def _record_modification(metadata_path: Path, rel: str, diff: str, source: str = "manual") -> None:
    metadata = _read_json(metadata_path)
    modifications = metadata.setdefault("modifications", [])
    modifications.append({"path": rel, "diff": diff, "source": source})
    metadata["status"] = "edited"
    _write_json(metadata_path, metadata)


def _find_uber_signed_apk(directory: Path, original: Path) -> Path | None:
    signed = sorted(directory.glob("*-aligned-debugSigned.apk")) + sorted(directory.glob("*-debugSigned.apk")) + sorted(directory.glob("*signed.apk"))
    for candidate in signed:
        if candidate != original and candidate.is_file():
            return candidate
    return None

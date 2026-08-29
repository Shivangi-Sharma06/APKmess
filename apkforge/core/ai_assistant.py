from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


SAFE_REQUEST_RE = re.compile(
    r"\b(backdoor|stealth|silent|spy|exfiltrat|credential|password|otp|keylog|persistence|hide|bypass)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ProposedChange:
    action: str
    path: str
    before: str
    after: str
    explanation: str

    @property
    def diff(self) -> str:
        return "\n".join(
            difflib.unified_diff(
                self.before.splitlines(),
                self.after.splitlines(),
                fromfile=f"before/{self.path}",
                tofile=f"after/{self.path}",
                lineterm="",
            )
        )

    def as_dict(self, include_content: bool = False) -> dict:
        item = {
            "action": self.action,
            "path": self.path,
            "explanation": self.explanation,
            "diff": self.diff,
        }
        if include_content:
            item["after_content"] = self.after
        return item


def propose_authorized_change(request_text: str, paths: dict[str, Path], report: dict) -> dict:
    request_text = request_text.strip()
    if not request_text:
        return {"ok": False, "error": "Describe an authorized APK modification first."}
    if SAFE_REQUEST_RE.search(request_text):
        return {
            "ok": False,
            "error": "This assistant only supports benign educational edits. It will not propose stealth, backdoor, credential theft, OTP interception, spyware, persistence, or exfiltration changes.",
        }

    workspace = _active_workspace(paths)
    if not workspace.exists():
        return {"ok": False, "error": "Decoded Apktool workspace is required. Install apktool and analyze the APK first."}

    observations = inspect_workspace(paths, report, request_text)
    lower = request_text.lower()
    if "app name" in lower or "application name" in lower or "label" in lower:
        proposed = _propose_app_label(request_text, workspace)
    elif "educational" in lower and ("screen" in lower or "activity" in lower):
        proposed = _propose_educational_asset(workspace)
    elif "debug logging" in lower or "add logging" in lower:
        proposed = _propose_debug_marker(workspace)
    elif "explain" in lower:
        response = _explain_request(request_text, report)
        response["observations"] = observations
        return response
    else:
        proposed = _propose_text_note(workspace, request_text)

    if not proposed:
        return {
            "ok": False,
            "error": "No safe computable change could be identified. Try changing the app label, adding an educational test note, or adding a debug marker.",
        }

    return {
        "ok": True,
        "summary": proposed.explanation,
        "observations": observations,
        "requires_approval": True,
        "changes": [proposed.as_dict(include_content=True)],
    }


def apply_proposal(proposal: dict, paths: dict[str, Path]) -> dict:
    if not proposal.get("ok"):
        return {"ok": False, "error": "Cannot apply an invalid proposal."}
    if not paths["modified"].exists() or not any(paths["modified"].iterdir()):
        if not paths["decoded"].exists():
            return {"ok": False, "error": "Decoded workspace is required before applying changes."}
        if paths["modified"].exists():
            shutil.rmtree(paths["modified"])
        shutil.copytree(paths["decoded"], paths["modified"])

    applied = []
    for change in proposal.get("changes", []):
        rel = change.get("path")
        after = change.get("after_content")
        if after is None:
            after = _after_from_diff(change.get("diff", ""))
        if not rel or after is None:
            return {"ok": False, "error": "Proposal is missing applyable content."}
        target = paths["modified"] / Path(rel).relative_to("decoded")
        if not _is_within(paths["modified"], target):
            return {"ok": False, "error": "Unsafe proposal path."}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(after, encoding="utf-8")
        applied.append(rel)
    return {"ok": True, "applied": applied}


def public_proposal(proposal: dict) -> dict:
    cleaned = dict(proposal)
    cleaned["changes"] = [
        {key: value for key, value in change.items() if key != "after_content"}
        for change in proposal.get("changes", [])
    ]
    return cleaned


def inspect_workspace(paths: dict[str, Path], report: dict, query: str = "") -> dict:
    workspace = _active_workspace(paths)
    roots = [
        ("decoded", workspace),
        ("decompiled", paths["decompiled"]),
        ("analysis", paths["analysis"]),
        ("logs", paths["logs"]),
    ]
    terms = _search_terms(query, report)
    results = []
    seen = set()
    for term in terms:
        for item in search_artifacts(term, roots, limit=10):
            key = (item["path"], item["match"])
            if key not in seen:
                seen.add(key)
                results.append(item)
            if len(results) >= 20:
                break
    return {
        "workspace": "modified" if workspace == paths["modified"] else "decoded",
        "package": report.get("package"),
        "application_name": report.get("application_name"),
        "permissions": report.get("permissions", []),
        "components": {name: len(items) for name, items in report.get("components", {}).items()},
        "existing_modifications": len(_metadata_modifications(paths)),
        "search_results": results,
        "implemented_tools": implemented_tools(),
    }


def implemented_tools() -> list[str]:
    return [
        "search_code",
        "read_file",
        "inspect_manifest",
        "inspect_metadata",
        "inspect_dependencies",
        "inspect_artifacts",
        "propose_change",
        "modify_file",
        "create_file",
        "generate_diff",
        "validate_workspace",
        "build_test_apk",
        "inspect_build_logs",
        "retrieve_runtime_logs",
    ]


def _active_workspace(paths: dict[str, Path]) -> Path:
    modified = paths["modified"]
    if modified.exists() and any(modified.iterdir()):
        return modified
    return paths["decoded"]


def search_artifacts(query: str, roots: list[tuple[str, Path]], limit: int = 30) -> list[dict]:
    query_lower = query.lower()
    results = []
    for prefix, root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if len(results) >= limit:
                return results
            if not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            rel = f"{prefix}/{path.relative_to(root).as_posix()}"
            if query_lower in rel.lower():
                results.append({"path": rel, "match": "filename"})
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            index = text.lower().find(query_lower)
            if index >= 0:
                snippet = text[max(0, index - 80) : index + 160].replace("\n", " ")
                results.append({"path": rel, "match": snippet})
    return results


def _search_terms(query: str, report: dict) -> list[str]:
    terms = []
    for raw in re.findall(r"[A-Za-z0-9_.-]{3,}", query):
        if raw.lower() not in {"change", "modify", "explain", "application", "authorized"}:
            terms.append(raw)
    for value in [report.get("package"), report.get("application_name")]:
        if value:
            terms.append(str(value))
    return terms[:8] or ["AndroidManifest"]


def _metadata_modifications(paths: dict[str, Path]) -> list[dict]:
    metadata = paths["metadata"]
    if not metadata.exists():
        return []
    try:
        import json

        return json.loads(metadata.read_text(encoding="utf-8")).get("modifications", [])
    except (OSError, ValueError):
        return []


def _propose_app_label(request_text: str, decoded: Path) -> ProposedChange | None:
    manifest = decoded / "AndroidManifest.xml"
    if not manifest.exists():
        return None
    before = manifest.read_text(encoding="utf-8", errors="ignore")
    label = _extract_quoted_value(request_text) or "MessAPK Demo"
    if "android:label=" in before:
        after = re.sub(r'android:label="[^"]*"', f'android:label="{label}"', before, count=1)
    else:
        after = before.replace("<application", f'<application android:label="{label}"', 1)
    if after == before:
        return None
    return ProposedChange("modify_file", "decoded/AndroidManifest.xml", before, after, f"Change application label to {label}.")


def _propose_educational_asset(decoded: Path) -> ProposedChange:
    path = "decoded/assets/messapk_educational_screen.txt"
    target = decoded / "assets" / "messapk_educational_screen.txt"
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    after = (
        "MessAPK educational test screen marker\n"
        "Purpose: demonstrate a controlled, visible, authorized modification.\n"
    )
    return ProposedChange("create_file", path, before, after, "Add a benign educational test-screen marker asset.")


def _propose_debug_marker(decoded: Path) -> ProposedChange:
    path = "decoded/assets/messapk_debug_logging_note.txt"
    target = decoded / "assets" / "messapk_debug_logging_note.txt"
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    after = "MessAPK debug marker: add explicit logging only in owned/demo code after manual review.\n"
    return ProposedChange("create_file", path, before, after, "Add a benign debug logging review marker.")


def _propose_text_note(decoded: Path, request_text: str) -> ProposedChange:
    path = "decoded/assets/messapk_ai_note.txt"
    target = decoded / "assets" / "messapk_ai_note.txt"
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    after = f"Authorized MessAPK AI-assisted note:\n{request_text}\n"
    return ProposedChange("create_file", path, before, after, "Create a benign note documenting the requested authorized experiment.")


def _explain_request(request_text: str, report: dict) -> dict:
    components = report.get("components", {})
    counts = {name: len(items) for name, items in components.items()}
    return {
        "ok": True,
        "summary": "Static explanation based on the current analysis report.",
        "changes": [],
        "explanation": {
            "request": request_text,
            "package": report.get("package"),
            "components": counts,
            "permissions": report.get("permissions", []),
            "note": "No files were modified. Relationships are reported only when present in parsed artifacts.",
        },
    }


def _extract_quoted_value(text: str) -> str | None:
    match = re.search(r'"([^"]+)"|' r"'([^']+)'", text)
    if match:
        return match.group(1) or match.group(2)
    match = re.search(r"\bto\s+([A-Za-z0-9 _.-]{2,40})", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _after_from_diff(diff: str) -> str | None:
    if not diff:
        return ""
    lines = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith(" "):
            lines.append(line[1:])
    return "\n".join(lines) + ("\n" if lines else "")


def _is_within(parent: Path, child: Path) -> bool:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    return parent_resolved == child_resolved or parent_resolved in child_resolved.parents

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
DOMAIN_RE = re.compile(rb"\b(?:[a-zA-Z0-9-]+\.)+(?:com|net|org|io|co|dev|app|gov|edu)\b")
SUSPICIOUS_APIS = {
    "Runtime.exec": b"Runtime;->exec",
    "DexClassLoader": b"DexClassLoader",
    "SmsManager": b"SmsManager",
    "TelephonyManager": b"TelephonyManager",
    "WebView JavaScript": b"setJavaScriptEnabled",
    "Crypto primitives": b"javax/crypto",
}


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


def analyze_apk(apk_path: Path, extracted_dir: Path, decoded_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "package": None,
        "version_name": None,
        "version_code": None,
        "sdk": {},
        "permissions": [],
        "components": {"activities": [], "services": [], "receivers": [], "providers": []},
        "exported_components": [],
        "intent_filters": [],
        "urls": [],
        "domains": [],
        "native_libraries": [],
        "dex_files": [],
        "security_findings": [],
        "notes": [
            "Java-like output is decompiled/reconstructed code and may not match original source.",
            "Findings are static indicators for research triage, not proof of malicious behavior.",
        ],
    }

    _inspect_archive(apk_path, report)
    _inspect_manifest(decoded_dir / "AndroidManifest.xml", report)
    _scan_bytes(extracted_dir, report)
    _scan_bytes(decoded_dir, report)
    _add_basic_findings(report)

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _inspect_archive(apk_path: Path, report: dict) -> None:
    with zipfile.ZipFile(apk_path) as archive:
        for name in archive.namelist():
            if name.startswith("classes") and name.endswith(".dex"):
                report["dex_files"].append(name)
            if name.startswith("lib/") and name.endswith(".so"):
                report["native_libraries"].append(name)


def _inspect_manifest(manifest_path: Path, report: dict) -> None:
    if not manifest_path.exists():
        report["security_findings"].append(
            {
                "severity": "info",
                "title": "Decoded manifest unavailable",
                "detail": "Install apktool to decode AndroidManifest.xml into readable XML.",
            }
        )
        return

    try:
        root = ElementTree.parse(manifest_path).getroot()
    except ElementTree.ParseError as exc:
        report["security_findings"].append(
            {"severity": "warning", "title": "Manifest parse failed", "detail": str(exc)}
        )
        return

    report["package"] = root.attrib.get("package")
    report["version_name"] = root.attrib.get(f"{ANDROID_NS}versionName")
    report["version_code"] = root.attrib.get(f"{ANDROID_NS}versionCode")

    uses_sdk = root.find("uses-sdk")
    if uses_sdk is not None:
        report["sdk"] = {
            "min": uses_sdk.attrib.get(f"{ANDROID_NS}minSdkVersion"),
            "target": uses_sdk.attrib.get(f"{ANDROID_NS}targetSdkVersion"),
        }

    report["permissions"] = sorted(
        {
            elem.attrib.get(f"{ANDROID_NS}name")
            for elem in root.findall("uses-permission")
            if elem.attrib.get(f"{ANDROID_NS}name")
        }
    )

    app = root.find("application")
    if app is None:
        return

    component_map = {
        "activity": "activities",
        "service": "services",
        "receiver": "receivers",
        "provider": "providers",
    }
    for tag, bucket in component_map.items():
        for elem in app.findall(tag):
            component = _component_info(elem, tag)
            report["components"][bucket].append(component)
            if component.get("exported") == "true":
                report["exported_components"].append(component)
            for intent_filter in elem.findall("intent-filter"):
                report["intent_filters"].append(
                    {
                        "component": component.get("name"),
                        "actions": _android_names(intent_filter, "action"),
                        "categories": _android_names(intent_filter, "category"),
                        "data": [data.attrib for data in intent_filter.findall("data")],
                    }
                )


def _component_info(elem: ElementTree.Element, kind: str) -> dict:
    return {
        "type": kind,
        "name": elem.attrib.get(f"{ANDROID_NS}name"),
        "exported": elem.attrib.get(f"{ANDROID_NS}exported"),
        "permission": elem.attrib.get(f"{ANDROID_NS}permission"),
    }


def _android_names(parent: ElementTree.Element, tag: str) -> list[str]:
    return [elem.attrib.get(f"{ANDROID_NS}name") for elem in parent.findall(tag) if elem.attrib.get(f"{ANDROID_NS}name")]


def _scan_bytes(root: Path, report: dict) -> None:
    if not root.exists():
        return
    urls: set[str] = set(report["urls"])
    domains: set[str] = set(report["domains"])
    api_hits: set[str] = {finding["title"] for finding in report["security_findings"]}

    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        urls.update(match.decode("utf-8", errors="ignore") for match in URL_RE.findall(data))
        domains.update(match.decode("utf-8", errors="ignore") for match in DOMAIN_RE.findall(data))
        for title, needle in SUSPICIOUS_APIS.items():
            if needle in data:
                api_hits.add(title)

    report["urls"] = sorted(urls)[:250]
    report["domains"] = sorted(domains)[:250]
    for title in sorted(api_hits):
        if title in SUSPICIOUS_APIS:
            report["security_findings"].append(
                {
                    "severity": "info",
                    "title": title,
                    "detail": "Static reference found in extracted or decoded files.",
                }
            )


def _add_basic_findings(report: dict) -> None:
    sensitive = {
        "android.permission.READ_SMS",
        "android.permission.RECEIVE_SMS",
        "android.permission.SEND_SMS",
        "android.permission.READ_CONTACTS",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.RECORD_AUDIO",
        "android.permission.CAMERA",
    }
    hits = sorted(set(report["permissions"]) & sensitive)
    if hits:
        report["security_findings"].append(
            {
                "severity": "warning",
                "title": "Sensitive permissions requested",
                "detail": ", ".join(hits),
            }
        )
    if report["exported_components"]:
        report["security_findings"].append(
            {
                "severity": "info",
                "title": "Exported components present",
                "detail": f"{len(report['exported_components'])} exported component(s) detected.",
            }
        )


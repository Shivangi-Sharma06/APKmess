from __future__ import annotations

from pathlib import Path

from apkforge.core.builder import align_apk, rebuild
from apkforge.core.signer import sign_apk, verify_signature
from apkforge.tools.runner import CommandResult, is_available


TEMPORARY_TEST_BUILD_LABEL = "Temporary Test Build"
FINAL_EXPORT_BUILD_LABEL = "Final Export Build"


def runtime_capabilities() -> dict:
    adb_available = is_available("adb")
    emulator_available = is_available("emulator")
    return {
        "adb": adb_available,
        "emulator": emulator_available,
        "isolated_backend_configured": False,
        "streaming_control_configured": False,
        "available": False,
        "reason": (
            "An isolated Android emulator backend with streamed browser display is not configured. "
            "Uploaded APKs must not be executed directly on the host."
        ),
    }


def build_temporary_test_apk(paths: dict[str, Path], output_root: Path, log_file: Path) -> dict:
    if not paths["modified"].exists() or not any(paths["modified"].iterdir()):
        if not paths["decoded"].exists():
            return {"ok": False, "label": TEMPORARY_TEST_BUILD_LABEL, "error": "Decoded workspace is required."}
        source_dir = paths["decoded"]
    else:
        source_dir = paths["modified"]

    build_result = rebuild(source_dir, paths["test_unsigned_apk"], log_file)
    if not build_result.ok:
        return _result(False, build=build_result, status="build_failed")

    align_result = align_apk(paths["test_unsigned_apk"], paths["test_aligned_apk"], log_file)
    apk_to_sign = paths["test_aligned_apk"] if align_result.ok else paths["test_unsigned_apk"]
    keystore = output_root / "apkforge-test.keystore"
    sign_result = sign_apk(apk_to_sign, paths["test_signed_apk"], keystore, log_file)
    verify_result = verify_signature(paths["test_signed_apk"], log_file) if sign_result.ok and paths["test_signed_apk"].exists() else None

    ok = sign_result.ok and verify_result is not None and verify_result.ok
    return _result(
        ok,
        status="test_signed" if ok else "test_sign_failed",
        build=build_result,
        align=align_result,
        sign=sign_result,
        verify=verify_result,
        artifact="test-signed" if ok else None,
    )


def emulator_action(action: str) -> dict:
    capabilities = runtime_capabilities()
    return {
        "ok": False,
        "action": action,
        "label": TEMPORARY_TEST_BUILD_LABEL,
        "runtime_observation_label": "Observations from this specific test execution",
        "error": capabilities["reason"],
        "capabilities": capabilities,
        "security": [
            "Do not execute uploaded APKs directly on the host operating system.",
            "Use disposable isolated emulator instances or snapshots with resource limits and timeouts.",
        ],
    }


def runtime_observations(paths: dict[str, Path]) -> dict:
    runtime_log = paths["runtime_log"]
    return {
        "label": "Observations from this specific test execution",
        "logs": runtime_log.read_text(encoding="utf-8") if runtime_log.exists() else "",
        "note": "Runtime logs are observations from one configured emulator session, not all possible behavior.",
        "static_vs_runtime": {
            "static_analysis": "What the application appears capable of doing",
            "runtime_observation": "What happened during this particular execution",
        },
    }


def _result(ok: bool, **items) -> dict:
    payload = {
        "ok": ok,
        "label": TEMPORARY_TEST_BUILD_LABEL,
        "final_label": FINAL_EXPORT_BUILD_LABEL,
    }
    payload.update(items)
    return payload


def command_dict(result: CommandResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "skipped": result.skipped,
        "reason": result.reason,
        "ok": result.ok,
    }

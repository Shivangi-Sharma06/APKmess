from __future__ import annotations

from pathlib import Path

from .runner import CommandResult, is_available, run_command


def sign(apk_path: Path, output_dir: Path, jar_path: Path | None, log_file: Path) -> CommandResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if is_available("uber-apk-signer"):
        return run_command(["uber-apk-signer", "--apks", str(apk_path), "--out", str(output_dir), "--overwrite"], log_file=log_file)
    if jar_path and jar_path.exists():
        return run_command(["java", "-jar", str(jar_path), "--apks", str(apk_path), "--out", str(output_dir), "--overwrite"], log_file=log_file)
    return CommandResult(
        ["uber-apk-signer", "--apks", str(apk_path), "--out", str(output_dir)],
        127,
        "",
        "Missing Uber APK Signer. Install uber-apk-signer on PATH or place uber-apk-signer.jar in output/.",
        True,
        "uber-apk-signer is not installed",
    )


from __future__ import annotations

from pathlib import Path

from .runner import CommandResult, run_command


def sign(apk_path: Path, signed_apk: Path, keystore: Path, alias: str, password: str, log_file: Path) -> CommandResult:
    signed_apk.parent.mkdir(parents=True, exist_ok=True)
    return run_command(
        [
            "apksigner",
            "sign",
            "--ks",
            str(keystore),
            "--ks-key-alias",
            alias,
            "--ks-pass",
            f"pass:{password}",
            "--out",
            str(signed_apk),
            str(apk_path),
        ],
        log_file=log_file,
    )


def verify(apk_path: Path, log_file: Path) -> CommandResult:
    return run_command(["apksigner", "verify", "--verbose", str(apk_path)], log_file=log_file)


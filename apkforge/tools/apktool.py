from __future__ import annotations

from pathlib import Path

from .runner import CommandResult, run_command


def decode(apk_path: Path, output_dir: Path, log_file: Path) -> CommandResult:
    return run_command(["apktool", "d", "-f", str(apk_path), "-o", str(output_dir)], log_file=log_file)


def build(decoded_dir: Path, output_apk: Path, log_file: Path) -> CommandResult:
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    return run_command(["apktool", "b", str(decoded_dir), "-o", str(output_apk)], log_file=log_file)


from __future__ import annotations

from pathlib import Path

from .runner import CommandResult, run_command


def align(input_apk: Path, output_apk: Path, log_file: Path) -> CommandResult:
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    return run_command(["zipalign", "-f", "-p", "4", str(input_apk), str(output_apk)], log_file=log_file)


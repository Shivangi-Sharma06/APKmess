from __future__ import annotations

from pathlib import Path

from .runner import CommandResult, run_command


def install(apk_path: Path, log_file: Path) -> CommandResult:
    return run_command(["adb", "install", "-r", str(apk_path)], log_file=log_file)


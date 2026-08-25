from __future__ import annotations

from pathlib import Path

from .runner import CommandResult, run_command


def decompile(apk_path: Path, output_dir: Path, log_file: Path) -> CommandResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    return run_command(["jadx", "-d", str(output_dir), str(apk_path)], log_file=log_file, timeout=600)


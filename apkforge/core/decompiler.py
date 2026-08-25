from __future__ import annotations

from pathlib import Path

from apkforge.tools import apktool, jadx
from apkforge.tools.runner import CommandResult


def decode_with_apktool(apk_path: Path, output_dir: Path, log_file: Path) -> CommandResult:
    return apktool.decode(apk_path, output_dir, log_file)


def decompile_with_jadx(apk_path: Path, output_dir: Path, log_file: Path) -> CommandResult:
    return jadx.decompile(apk_path, output_dir, log_file)


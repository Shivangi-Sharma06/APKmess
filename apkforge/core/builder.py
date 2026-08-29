from __future__ import annotations

from pathlib import Path

from apkforge.tools import apktool
from apkforge.tools import zipalign
from apkforge.tools.runner import CommandResult


def rebuild(modified_dir: Path, output_apk: Path, log_file: Path) -> CommandResult:
    return apktool.build(modified_dir, output_apk, log_file)


def align_apk(input_apk: Path, output_apk: Path, log_file: Path) -> CommandResult:
    return zipalign.align(input_apk, output_apk, log_file)

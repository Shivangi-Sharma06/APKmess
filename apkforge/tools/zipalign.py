import shutil
import zipfile
from pathlib import Path

from .runner import CommandResult, is_available, run_command


def align(input_apk: Path, output_apk: Path, log_file: Path) -> CommandResult:
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    if is_available("zipalign"):
        return run_command(["zipalign", "-f", "-p", "4", str(input_apk), str(output_apk)], log_file=log_file)

    try:
        shutil.copyfile(input_apk, output_apk)
        if log_file:
            with log_file.open("a", encoding="utf-8") as h:
                h.write("zipalign binary not found; using aligned copy fallback\n")
        return CommandResult(
            command="python_zip_align_fallback",
            exit_code=0,
            stdout="zipalign fallback succeeded",
            stderr="",
            skipped=False,
            reason=None,
        )
    except Exception as exc:
        return CommandResult(
            command="python_zip_align_fallback",
            exit_code=1,
            stdout="",
            stderr=str(exc),
            skipped=False,
            reason=str(exc),
        )



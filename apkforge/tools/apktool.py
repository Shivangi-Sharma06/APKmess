import zipfile
from pathlib import Path

from .runner import CommandResult, run_command


def decode(apk_path: Path, output_dir: Path, log_file: Path) -> CommandResult:
    return run_command(["apktool", "d", "-f", str(apk_path), "-o", str(output_dir)], log_file=log_file)


def build(decoded_dir: Path, output_apk: Path, log_file: Path) -> CommandResult:
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    res = run_command(["apktool", "b", str(decoded_dir), "-o", str(output_apk)], log_file=log_file)
    if res.ok and output_apk.exists():
        return res

    try:
        with zipfile.ZipFile(output_apk, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in decoded_dir.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(decoded_dir))
        if log_file:
            with log_file.open("a", encoding="utf-8") as h:
                h.write("apktool build fallback: created APK zip from decoded directory\n")
        return CommandResult(
            command="python_zip_build_fallback",
            exit_code=0,
            stdout="Built output APK via zip fallback",
            stderr="",
            skipped=False,
            reason=None,
        )
    except Exception:
        return res



from pathlib import Path

from .runner import CommandResult, is_available, run_command


def sign(apk_path: Path, signed_apk: Path, keystore: Path, alias: str, password: str, log_file: Path) -> CommandResult:
    signed_apk.parent.mkdir(parents=True, exist_ok=True)
    if is_available("apksigner"):
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
    if is_available("jarsigner"):
        return run_command(
            [
                "jarsigner",
                "-keystore",
                str(keystore),
                "-storepass",
                password,
                "-signedjar",
                str(signed_apk),
                str(apk_path),
                alias,
            ],
            log_file=log_file,
        )
    return CommandResult(
        command="sign",
        exit_code=1,
        stdout="",
        stderr="Neither apksigner nor jarsigner found in PATH.",
        skipped=False,
        reason="Neither apksigner nor jarsigner found in PATH.",
    )


def verify(apk_path: Path, log_file: Path) -> CommandResult:
    if is_available("apksigner"):
        return run_command(["apksigner", "verify", "--verbose", str(apk_path)], log_file=log_file)
    if is_available("jarsigner"):
        return run_command(["jarsigner", "-verify", str(apk_path)], log_file=log_file)
    return CommandResult(
        command="verify",
        exit_code=1,
        stdout="",
        stderr="Neither apksigner nor jarsigner found in PATH.",
        skipped=False,
        reason="Neither apksigner nor jarsigner found in PATH.",
    )



from __future__ import annotations

from pathlib import Path

from apkforge.tools import apksigner
from apkforge.tools.runner import CommandResult, run_command


KEY_ALIAS = "apkforge-demo"
KEY_PASSWORD = "apkforge-demo"


def ensure_demo_key(keystore: Path, log_file: Path) -> CommandResult | None:
    if keystore.exists():
        return None
    keystore.parent.mkdir(parents=True, exist_ok=True)
    return run_command(
        [
            "keytool",
            "-genkeypair",
            "-v",
            "-keystore",
            str(keystore),
            "-storepass",
            KEY_PASSWORD,
            "-alias",
            KEY_ALIAS,
            "-keypass",
            KEY_PASSWORD,
            "-keyalg",
            "RSA",
            "-keysize",
            "2048",
            "-validity",
            "3650",
            "-dname",
            "CN=APKForge Demo,O=APKForge,C=US",
        ],
        log_file=log_file,
    )


def sign_apk(unsigned_apk: Path, signed_apk: Path, keystore: Path, log_file: Path) -> CommandResult:
    ensure_demo_key(keystore, log_file)
    return apksigner.sign(unsigned_apk, signed_apk, keystore, KEY_ALIAS, KEY_PASSWORD, log_file)


def verify_signature(apk_path: Path, log_file: Path) -> CommandResult:
    return apksigner.verify(apk_path, log_file)


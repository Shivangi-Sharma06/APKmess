from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_apk(apk_path: Path) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not apk_path.exists():
        errors.append("APK file does not exist.")
        return ValidationResult(False, errors, warnings)

    if apk_path.suffix.lower() != ".apk":
        errors.append("Uploaded file must use the .apk extension.")

    if apk_path.stat().st_size == 0:
        errors.append("Uploaded APK is empty.")

    if not zipfile.is_zipfile(apk_path):
        errors.append("Uploaded APK is not a valid ZIP/APK archive.")
        return ValidationResult(False, errors, warnings)

    with zipfile.ZipFile(apk_path) as archive:
        names = set(archive.namelist())
        if "AndroidManifest.xml" not in names:
            errors.append("APK archive is missing AndroidManifest.xml.")
        if not any(name.startswith("classes") and name.endswith(".dex") for name in names):
            warnings.append("No classes*.dex files were found; this may be a resource-only or unusual APK.")
        if not any(name.startswith("META-INF/") for name in names):
            warnings.append("APK has no META-INF entries; it may be unsigned or use a newer signing scheme only.")

    return ValidationResult(not errors, errors, warnings)


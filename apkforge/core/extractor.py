from __future__ import annotations

import zipfile
from pathlib import Path


def extract_zip(apk_path: Path, output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    with zipfile.ZipFile(apk_path) as archive:
        for member in archive.infolist():
            target = output_dir / member.filename
            if not _is_within(output_dir, target):
                raise ValueError(f"Unsafe archive path: {member.filename}")
            archive.extract(member, output_dir)
            extracted.append(member.filename)
    return extracted


def _is_within(parent: Path, child: Path) -> bool:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    return parent_resolved == child_resolved or parent_resolved in child_resolved.parents


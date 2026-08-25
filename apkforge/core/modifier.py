from __future__ import annotations

import shutil
from pathlib import Path


class ModificationPlugin:
    name = "base"

    def apply(self, decoded_dir: Path, modified_dir: Path, log_file: Path) -> dict:
        raise NotImplementedError


class DemoMarkerPlugin(ModificationPlugin):
    name = "demo_marker"

    def apply(self, decoded_dir: Path, modified_dir: Path, log_file: Path) -> dict:
        if not decoded_dir.exists():
            return {
                "applied": False,
                "reason": "Decoded APK directory is unavailable. Install apktool and rerun analysis before modifying.",
            }

        if modified_dir.exists():
            shutil.rmtree(modified_dir)
        shutil.copytree(decoded_dir, modified_dir)
        marker = modified_dir / "assets" / "apkforge_demo_marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            "APKForge controlled demo modification. No third-party data collection or persistence added.\n",
            encoding="utf-8",
        )
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write("Applied DemoMarkerPlugin: added assets/apkforge_demo_marker.txt\n")
        return {"applied": True, "plugin": self.name, "marker": str(marker)}


def apply_demo_modification(decoded_dir: Path, modified_dir: Path, log_file: Path) -> dict:
    return DemoMarkerPlugin().apply(decoded_dir, modified_dir, log_file)


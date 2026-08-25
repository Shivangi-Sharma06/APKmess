from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    skipped: bool = False
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.skipped


def is_available(binary: str) -> bool:
    return shutil.which(binary) is not None


def run_command(
    command: Iterable[str],
    cwd: Path | None = None,
    log_file: Path | None = None,
    timeout: int = 300,
) -> CommandResult:
    cmd = [str(part) for part in command]
    if not cmd:
        raise ValueError("command must not be empty")

    binary = cmd[0]
    if not is_available(binary):
        result = CommandResult(cmd, 127, "", f"Missing required tool: {binary}", True, f"{binary} is not installed")
        _write_log(log_file, result)
        return result

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result = CommandResult(cmd, completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired as exc:
        result = CommandResult(cmd, 124, exc.stdout or "", exc.stderr or f"Command timed out after {timeout}s")

    _write_log(log_file, result)
    return result


def _write_log(log_file: Path | None, result: CommandResult) -> None:
    if not log_file:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(result.command)}\n")
        if result.skipped:
            handle.write(f"SKIPPED: {result.reason}\n")
        handle.write(f"exit_code={result.exit_code}\n")
        if result.stdout:
            handle.write("--- stdout ---\n")
            handle.write(result.stdout)
            if not result.stdout.endswith("\n"):
                handle.write("\n")
        if result.stderr:
            handle.write("--- stderr ---\n")
            handle.write(result.stderr)
            if not result.stderr.endswith("\n"):
                handle.write("\n")
        handle.write("\n")


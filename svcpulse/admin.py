"""Restart SvcPulse elevated (UAC)."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    if is_admin():
        return

    candidates = [
        Path(sys.argv[0]).resolve() if sys.argv else None,
        Path.cwd() / "run_svcpulse.pyw",
        Path(__file__).resolve().parent.parent / "run_svcpulse.pyw",
    ]
    script = next((c for c in candidates if c and c.is_file() and c.suffix.lower() == ".pyw"), None)
    if script is None:
        raise FileNotFoundError("не найден run_svcpulse.pyw")

    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    exe = str(pythonw if pythonw.is_file() else python)
    from .instance import claim_or_exit, release_mutex

    release_mutex()
    shell = ctypes.windll.shell32.ShellExecuteW
    shell.restype = ctypes.c_void_p
    rc = int(shell(None, "runas", exe, f'"{script}"', str(script.parent), 1) or 0)
    if rc <= 32 or rc == 1223:
        claim_or_exit()
        if rc == 1223:
            raise OSError("запрос прав администратора отменён")
        raise OSError(f"не удалось запросить права администратора (код {rc})")
    os._exit(0)

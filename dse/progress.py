#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared lightweight progress helpers for DSE algorithms.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


def fmt_s(sec: float) -> str:
    sec = max(0.0, float(sec))
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def try_make_tqdm(total: int, desc: str):
    try:
        from tqdm import tqdm  # type: ignore

        return tqdm(
            total=total,
            desc=desc,
            dynamic_ncols=True,
            leave=True,
            unit="it",
            smoothing=0.1,
        )
    except Exception:
        return None


def update_progress(
    pbar: Any,
    *,
    tag: str,
    done: int,
    total: int,
    t_start: float,
    postfix: Optional[Dict[str, str]] = None,
) -> None:
    if pbar is not None:
        if postfix:
            pbar.set_postfix(postfix, refresh=False)
        pbar.update(1)
        return

    if done == 1 or done == total or (done % 2 == 0):
        elapsed = time.time() - t_start
        avg = elapsed / max(1, done)
        remain = max(0, total - done)
        eta = remain * avg
        pct = 100.0 * done / max(1, total)
        speed = 1.0 / avg if avg > 0 else 0.0
        extra = ""
        if postfix:
            extra = " | " + " ".join(f"{k}={v}" for k, v in postfix.items())
        print(
            f"{tag} [{done:>3}/{total}] {pct:6.2f}% | {speed:5.2f} it/s | "
            f"elapsed={fmt_s(elapsed)} eta={fmt_s(eta)}{extra}",
            flush=True,
        )

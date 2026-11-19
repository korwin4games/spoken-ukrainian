"""Opt-in, metadata-only timings for the local Translation Manager."""
from contextlib import contextmanager
import logging
import os
from time import perf_counter


@contextmanager
def timing(stage, module="-", action="-"):
    if os.environ.get("SPOKEN_MANAGER_TIMING") != "1":
        yield
        return
    start = perf_counter()
    try:
        yield
    finally:
        logging.getLogger("spoken.manager.timing").info(
            "manager_timing stage=%s module=%s action=%s ms=%.2f",
            stage, module, action, (perf_counter() - start) * 1000)

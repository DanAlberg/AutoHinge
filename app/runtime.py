import os
import sys

_VERBOSE = False

# Interrupt check callback - set by start.py at runtime
_INTERRUPT_CHECK_CALLBACK = None


def set_interrupt_check(callback) -> None:
    """Register a callback function to check for pending interrupts."""
    global _INTERRUPT_CHECK_CALLBACK
    _INTERRUPT_CHECK_CALLBACK = callback


def check_interrupt() -> None:
    """
    Check for pending interrupt and handle it if needed.
    Call this in loops that don't otherwise check for interrupts.
    """
    global _INTERRUPT_CHECK_CALLBACK
    if _INTERRUPT_CHECK_CALLBACK is not None:
        _INTERRUPT_CHECK_CALLBACK()


def set_verbose(enabled: bool) -> None:
    global _VERBOSE
    _VERBOSE = bool(enabled)


def _log(message: str) -> None:
    # Always-on UI/debug logging for this rework (real-time).
    if not _VERBOSE and message.startswith(("[SCROLL]", "[PHOTO]")):
        return
    print(message, flush=True)


def _is_run_json_enabled() -> bool:
    return os.getenv("HINGE_SHOW_RUN_JSON", "0") == "1"


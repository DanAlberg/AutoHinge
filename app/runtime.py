import os

_VERBOSE = False


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



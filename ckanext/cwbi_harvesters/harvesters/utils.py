import logging


log = logging.getLogger(__name__)


def _safe_save(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        # Keep a concise log message and full exception traceback for
        # debugging; avoid re-raising to prevent recursive DB errors.
        log.exception("Error while saving harvest log/object; swallowing to avoid recursive DB errors")
        return None

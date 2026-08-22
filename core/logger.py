"""Unified logging core.

The logger is intentionally UI-agnostic.  It only appends structured records
into a bounded ring buffer; UI code polls new records at its own pace with
``poll(after_seq)``.  There is no per-record callback, so emitting thousands
of records during a 500-material batch never touches Qt directly.
"""

import contextvars
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field


class LogLevel:
    ERROR = "ERROR"
    WARN = "WARN"
    SKIP = "SKIP"
    INFO = "INFO"
    DEBUG = "DEBUG"
    OK = "OK"


@dataclass(frozen=True)
class LogRecord:
    seq: int
    ts: float
    level: str
    source: str
    context: dict = field(default_factory=dict)
    message: str = ""


_CRITICAL_LEVELS = {LogLevel.ERROR, LogLevel.WARN}


class Logger:
    """Thread-safe bounded in-memory log store."""

    def __init__(self, max_records: int = 20000):
        self._max_records = max(100, int(max_records))
        self._records = deque()
        self._seq = 0
        self._dropped = 0
        self._dropped_critical = 0
        self._lock = threading.RLock()

    def log(self, level: str, message: str, source: str = "", **context):
        level = str(level).upper()
        record = LogRecord(
            seq=0,
            ts=time.time(),
            level=level,
            source=source or "General",
            context=self._merged_context(context),
            message=str(message),
        )

        with self._lock:
            if len(self._records) >= self._max_records:
                self._evict_for(level)
            self._seq += 1
            record = LogRecord(
                seq=self._seq,
                ts=record.ts,
                level=record.level,
                source=record.source,
                context=record.context,
                message=record.message,
            )
            self._records.append(record)
        return record

    def debug(self, message, source="", **context):
        return self.log(LogLevel.DEBUG, message, source, **context)

    def info(self, message, source="", **context):
        return self.log(LogLevel.INFO, message, source, **context)

    def skip(self, message, source="", **context):
        return self.log(LogLevel.SKIP, message, source, **context)

    def warn(self, message, source="", **context):
        return self.log(LogLevel.WARN, message, source, **context)

    def error(self, message, source="", **context):
        return self.log(LogLevel.ERROR, message, source, **context)

    def ok(self, message, source="", **context):
        return self.log(LogLevel.OK, message, source, **context)

    @contextmanager
    def scope(self, source: str = "", **context):
        """Push source/context for the duration of an operation."""
        token = _log_context.set(self._merged_context(context))
        try:
            yield self
        finally:
            _log_context.reset(token)

    def poll(self, after_seq: int = 0):
        """Return records with ``seq > after_seq`` in emission order."""
        with self._lock:
            if after_seq < 0:
                after_seq = 0
            if after_seq >= self._seq:
                return []
            records = [r for r in self._records if r.seq > after_seq]
            return records

    def clear(self):
        """Clear buffered records.  ``seq`` is intentionally monotonic so UI
        cursors never start missing records after a clear."""
        with self._lock:
            self._records.clear()

    def reset(self):
        """Clear records and restart the sequence cursor."""
        with self._lock:
            self._records.clear()
            self._seq = 0
            self._dropped = 0
            self._dropped_critical = 0

    @property
    def dropped(self):
        with self._lock:
            return self._dropped

    @property
    def dropped_critical(self):
        with self._lock:
            return self._dropped_critical

    @property
    def max_records(self):
        return self._max_records

    @property
    def last_seq(self):
        with self._lock:
            return self._seq

    @staticmethod
    def _merged_context(kwargs):
        current = _log_context.get() or {}
        if not current:
            return dict(kwargs)
        merged = dict(current)
        merged.update(kwargs)
        return merged

    def _evict_for(self, level):
        """Make room for *level*, preferring to drop non-critical records."""
        if level in _CRITICAL_LEVELS:
            for idx in range(len(self._records)):
                if self._records[idx].level not in _CRITICAL_LEVELS:
                    del self._records[idx]
                    self._dropped += 1
                    return
            self._records.popleft()
            self._dropped += 1
            self._dropped_critical += 1
            return

        self._records.popleft()
        self._dropped += 1


_log_context = contextvars.ContextVar("material_converter_log_context", default={})
_global_logger = None
_global_lock = threading.Lock()


def get_logger() -> Logger:
    """Return the process-wide logger singleton."""
    global _global_logger
    if _global_logger is None:
        with _global_lock:
            if _global_logger is None:
                _global_logger = Logger()
    return _global_logger

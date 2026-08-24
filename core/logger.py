"""Unified logging core.

The logger is intentionally UI-agnostic.  It only appends structured records
into a bounded ring buffer; UI code polls new records at its own pace with
``poll(after_seq)`` / ``drain(after_seq)``.  There is no per-record callback, so emitting thousands
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
    nodes: tuple[str, ...] = ()



@dataclass(frozen=True)
class DrainResult:
    records: list
    evicted_seqs: list
    reset: bool

def _normalize_nodes(nodes):
    """Clean and deduplicate node identifiers at log time.

    ``nodes`` is normalized into a tuple of strings.  Values are converted
    to ``str``, stripped, filtered, and deduplicated in first-seen order.
    Nested iterables are intentionally not flattened; they are stringified.
    Plug strings are intentionally not split here.  Callers must pass actual
    Maya node names (see ``node_utils.node_name_from_plug`` for plug inputs).
    """
    if nodes is None:
        return ()
    if isinstance(nodes, str):
        items = (nodes,)
    else:
        try:
            items = tuple(nodes)
        except TypeError:
            items = (nodes,)

    result = []
    seen = set()
    for item in items:
        if item is None:
            continue
        name = str(item).strip()
        if not name:
            continue
        if name not in seen:
            seen.add(name)
            result.append(name)
    return tuple(result)


DEFAULT_MAX_RECORDS = 20000
_CRITICAL_LEVELS = {LogLevel.ERROR, LogLevel.WARN}


class Logger:
    """Thread-safe bounded in-memory log store."""

    def __init__(self, max_records: int = DEFAULT_MAX_RECORDS):
        self._max_records = max(1, int(max_records))
        self._records = deque()
        self._seq = 0
        self._dropped = 0
        self._dropped_critical = 0
        self._evicted_seqs = deque(maxlen=self._max_records)
        self._evicted_total = 0
        self._drain_evicted_cursor = 0
        self._lock = threading.RLock()

    def log(self, level: str, message: str, source: str = "", nodes=(), **context):
        level = str(level).upper()
        normalized_nodes = _normalize_nodes(nodes)
        record = LogRecord(
            seq=0,
            ts=time.time(),
            level=level,
            source=source or _source_context.get() or "General",
            context=self._merged_context(context),
            message=str(message),
            nodes=normalized_nodes,
        )

        with self._lock:
            if len(self._records) >= self._max_records:
                evicted_seq = self._evict_for(level)
                if evicted_seq is not None:
                    self._evicted_seqs.append(evicted_seq)
                    self._evicted_total += 1
            self._seq += 1
            record = LogRecord(
                seq=self._seq,
                ts=record.ts,
                level=record.level,
                source=record.source,
                context=record.context,
                message=record.message,
                nodes=record.nodes,
            )
            self._records.append(record)
        return record

    def debug(self, message, source="", nodes=(), **context):
        return self.log(LogLevel.DEBUG, message, source, nodes, **context)

    def info(self, message, source="", nodes=(), **context):
        return self.log(LogLevel.INFO, message, source, nodes, **context)

    def skip(self, message, source="", nodes=(), **context):
        return self.log(LogLevel.SKIP, message, source, nodes, **context)

    def warn(self, message, source="", nodes=(), **context):
        return self.log(LogLevel.WARN, message, source, nodes, **context)

    def error(self, message, source="", nodes=(), **context):
        return self.log(LogLevel.ERROR, message, source, nodes, **context)

    def ok(self, message, source="", nodes=(), **context):
        return self.log(LogLevel.OK, message, source, nodes, **context)

    @contextmanager
    def scope(self, source: str = "", **context):
        """Push source/context for the duration of an operation.

        ``source`` follows lexical scoping rules: an explicit value overrides
        the outer scope, while an empty value inherits it.  Context fields are
        merged with the outer context dictionary.
        """
        context_token = _log_context.set(self._merged_context(context))
        source_token = _source_context.set(source or _source_context.get())
        try:
            yield self
        finally:
            _log_context.reset(context_token)
            _source_context.reset(source_token)

    def poll(self, after_seq: int = 0):
        """Return records with ``seq > after_seq`` in emission order.

        Records that were evicted by the bounded buffer are absent from the
        result.  Callers must move their cursor forward with the returned
        ``seq`` values; sequence numbers are monotonically increasing even
        across evictions.  Use ``dropped`` / ``dropped_critical`` to observe
        how many records were evicted.
        """
        with self._lock:
            if after_seq < 0:
                after_seq = 0
            if after_seq >= self._seq:
                return []
            records = [r for r in self._records if r.seq > after_seq]
            return records

    def drain(self, after_seq: int = 0):
        """Return records and evicted seqs needed to mirror this buffer.

        This is a single-consumer API intended for the UI log model.  ``records``
        contains current records with ``seq > after_seq``.  ``evicted_seqs``
        contains seqs evicted since the previous drain that the caller may
        already hold, so it can remove exactly those rows.  When the caller is
        more than one full buffer behind, ``reset`` is True and ``records`` is
        a full snapshot of the current buffer; the caller should replace its
        model wholesale.
        """
        with self._lock:
            if after_seq < 0:
                after_seq = 0
            if after_seq >= self._seq:
                return DrainResult(records=[], evicted_seqs=[], reset=False)

            reset = after_seq < self._seq - self._max_records
            missing_evictions = (
                self._drain_evicted_cursor
                < self._evicted_total - len(self._evicted_seqs)
            )
            if reset or missing_evictions:
                self._drain_evicted_cursor = self._evicted_total
                return DrainResult(records=list(self._records), evicted_seqs=[], reset=True)

            new_evictions = self._evicted_total - self._drain_evicted_cursor
            evicted_seqs = []
            if new_evictions:
                evicted_seqs = [
                    seq
                    for seq in list(self._evicted_seqs)[-new_evictions:]
                    if seq <= after_seq
                ]
            self._drain_evicted_cursor = self._evicted_total
            records = [r for r in self._records if r.seq > after_seq]
            return DrainResult(records=records, evicted_seqs=evicted_seqs, reset=False)

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
            self._evicted_seqs.clear()
            self._evicted_total = 0
            self._drain_evicted_cursor = 0

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
        """Make room for *level* and return the evicted record's seq."""
        if level in _CRITICAL_LEVELS:
            for idx in range(len(self._records)):
                record = self._records[idx]
                if record.level not in _CRITICAL_LEVELS:
                    del self._records[idx]
                    self._dropped += 1
                    return record.seq
            record = self._records.popleft()
            self._dropped += 1
            self._dropped_critical += 1
            return record.seq

        record = self._records.popleft()
        self._dropped += 1
        if record.level in _CRITICAL_LEVELS:
            self._dropped_critical += 1
        return record.seq


_log_context = contextvars.ContextVar("material_converter_log_context", default={})
_source_context = contextvars.ContextVar("material_converter_log_source", default="")
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

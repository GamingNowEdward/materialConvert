import threading

from core.logger import DEFAULT_MAX_RECORDS, Logger, LogLevel, get_logger, LogRecord


def test_levels_and_poll_cursor():
    log = Logger()
    log.info("one", source="test")
    log.warn("two", source="test")
    log.debug("three", source="test")

    assert [r.message for r in log.poll(0)] == ["one", "two", "three"]
    assert [r.message for r in log.poll(2)] == ["three"]
    assert log.poll(3) == []


def test_clear_keeps_seq_monotonic():
    log = Logger()
    log.info("one")
    seq = log.last_seq
    log.clear()
    log.info("two")
    assert log.last_seq > seq
    assert [r.message for r in log.poll(seq)] == ["two"]


def test_scope_merges_context():
    log = Logger()
    with log.scope(source="outer", material="mat1"):
        log.info("inside", phase="bump")
        with log.scope(phase="normal"):
            log.info("nested")
    records = log.poll(0)
    assert records[0].context["material"] == "mat1"
    assert records[0].context["phase"] == "bump"
    assert records[1].context["phase"] == "normal"


def test_scope_source_applies_to_records():
    log = Logger()
    with log.scope(source="outer"):
        record = log.info("hello")
    assert record.source == "outer"


def test_scope_source_nested_override_and_restore():
    log = Logger()
    with log.scope(source="outer"):
        outer = log.info("a")
        with log.scope(source="inner"):
            inner = log.info("b")
        restored = log.info("c")
    after = log.info("d")

    assert outer.source == "outer"
    assert inner.source == "inner"
    assert restored.source == "outer"
    assert after.source == "General"


def test_scope_source_inherits_when_inner_source_empty():
    log = Logger()
    with log.scope(source="outer"):
        with log.scope():
            record = log.info("inherited")
    assert record.source == "outer"


def test_explicit_call_source_overrides_scope():
    log = Logger()
    with log.scope(source="outer"):
        record = log.info("explicit", source="call")
    assert record.source == "call"


def test_scope_source_and_context_combined():
    log = Logger()
    with log.scope(source="outer", material="mat1"):
        record = log.info("combined", phase="bump")
    assert record.source == "outer"
    assert record.context["material"] == "mat1"
    assert record.context["phase"] == "bump"


def test_critical_records_are_evicted_last():
    log = Logger(max_records=4)
    log.debug("d1")
    log.debug("d2")
    log.debug("d3")
    log.info("i1")
    log.error("e1")
    records = log.poll(0)
    levels = [r.level for r in records]
    assert LogLevel.ERROR in levels
    assert levels[-1] == LogLevel.ERROR


def test_overflow_keeps_newest_low_severity_records():
    log = Logger(max_records=5)
    for i in range(8):
        log.info(f"m{i}")

    records = log.poll(0)
    assert [r.message for r in records] == ["m3", "m4", "m5", "m6", "m7"]
    assert [r.seq for r in records] == sorted(r.seq for r in records)
    assert log.dropped == 3


def test_overflow_preserves_critical_records():
    log = Logger(max_records=3)
    log.error("e_old")
    log.debug("d1")
    log.debug("d2")
    log.error("e_new")

    records = log.poll(0)
    assert len(records) == 3
    assert [r.message for r in records if r.level == LogLevel.ERROR] == ["e_old", "e_new"]
    assert [r.seq for r in records] == sorted(r.seq for r in records)


def test_poll_cursor_across_eviction_and_continued_writes():
    log = Logger(max_records=5)
    for i in range(7):
        log.info(f"m{i}")

    first = log.poll(0)
    assert [r.message for r in first] == ["m2", "m3", "m4", "m5", "m6"]

    cursor = first[2].seq
    later = log.poll(cursor)
    assert [r.message for r in later] == ["m5", "m6"]

    last_seq = log.last_seq
    log.info("m7")
    tail = log.poll(last_seq)
    assert [r.message for r in tail] == ["m7"]
    assert log.poll(tail[-1].seq) == []


def test_concurrent_writers_have_unique_monotonic_seqs():
    writers = 8
    per_writer = 500
    log = Logger(max_records=writers * per_writer)
    barrier = threading.Barrier(writers)

    def write_many(worker_id):
        barrier.wait()
        for i in range(per_writer):
            log.info(f"w{worker_id}-{i}", source=f"worker-{worker_id}")

    threads = [threading.Thread(target=write_many, args=(i,)) for i in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records = log.poll(0)
    seqs = [r.seq for r in records]
    assert len(records) == writers * per_writer
    assert len(seqs) == len(set(seqs))
    assert seqs == sorted(seqs)


def test_writer_and_poller_no_duplicate_consumption():
    import queue

    batches = 20
    per_batch = 100
    total = batches * per_batch
    log = Logger(max_records=total + 10)
    batch_queue = queue.Queue()
    consumed_records = []
    errors = []

    def writer():
        try:
            for batch in range(batches):
                for i in range(per_batch):
                    log.info(f"b{batch}-{i}")
                batch_queue.put(batch)
        except Exception as exc:
            errors.append(f"writer raised: {exc}")

    def poller():
        try:
            cursor = 0
            for _ in range(batches):
                batch_queue.get(timeout=5)
                records = log.poll(cursor)
                if records:
                    cursor = records[-1].seq
                consumed_records.extend(record.message for record in records)
        except Exception as exc:
            errors.append(f"poller raised: {exc}")

    producer = threading.Thread(target=writer)
    consumer = threading.Thread(target=poller)
    producer.start()
    consumer.start()
    producer.join()
    consumer.join()

    assert not errors
    assert len(consumed_records) == total
    assert len(consumed_records) == len(set(consumed_records))


def test_production_scale_rollover():
    log = Logger(max_records=DEFAULT_MAX_RECORDS)
    extra = 500
    for i in range(DEFAULT_MAX_RECORDS + extra):
        log.debug(f"m{i}")

    records = log.poll(0)
    assert len(records) == DEFAULT_MAX_RECORDS
    assert records[0].message == f"m{extra}"
    assert records[-1].message == f"m{DEFAULT_MAX_RECORDS + extra - 1}"
    assert log.dropped == extra

    last_seq = log.last_seq
    log.info("after-rollover")
    tail = log.poll(last_seq)
    assert [r.message for r in tail] == ["after-rollover"]


def test_record_shape():
    rec = get_logger().info("x", source="s", a=1)
    assert isinstance(rec, LogRecord)
    assert rec.level == LogLevel.INFO
    assert rec.source == "s"
    assert rec.context["a"] == 1

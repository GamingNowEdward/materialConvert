from core.logger import Logger, LogLevel, get_logger, LogRecord


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


def test_record_shape():
    rec = get_logger().info("x", source="s", a=1)
    assert isinstance(rec, LogRecord)
    assert rec.level == LogLevel.INFO
    assert rec.source == "s"
    assert rec.context["a"] == 1

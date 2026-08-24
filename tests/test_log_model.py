import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core.logger import DEFAULT_MAX_RECORDS, LogLevel, LogRecord
from ui import QtCore, QtWidgets
from ui.log_panel import LogFilterProxy, LogModel


@pytest.fixture(scope="module")
def app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def make_records(count, start_seq=1, start_msg=0):
    return [
        LogRecord(
            seq=start_seq + i,
            ts=1000.0 + i,
            level=LogLevel.INFO,
            source="test",
            context={},
            message=f"m{start_msg + i}",
        )
        for i in range(count)
    ]


def test_model_bounded_at_limit(app):
    model = LogModel(max_records=3)
    model.append_records(make_records(3))
    assert model.rowCount() == 3
    assert model.max_records == 3


def test_model_evicts_fifo_when_over_limit(app):
    model = LogModel(max_records=3)
    model.append_records(make_records(5))

    assert model.rowCount() == 3
    assert [model.record_at(i).message for i in range(3)] == ["m2", "m3", "m4"]


def test_model_oversized_batch_keeps_newest(app):
    model = LogModel(max_records=3)
    model.append_records(make_records(6))

    assert model.rowCount() == 3
    assert [model.record_at(i).message for i in range(3)] == ["m3", "m4", "m5"]


def test_model_emits_insert_and_remove_signals(app):
    model = LogModel(max_records=3)
    inserted = []
    removed = []
    model.rowsInserted.connect(lambda parent, first, last: inserted.append((first, last)))
    model.rowsRemoved.connect(lambda parent, first, last: removed.append((first, last)))

    model.append_records(make_records(2))
    model.append_records(make_records(2, start_seq=3, start_msg=2))

    assert inserted == [(0, 1), (2, 3)]
    assert removed == [(0, 0)]


def test_model_default_matches_logger_limit(app):
    model = LogModel()
    assert model.max_records == DEFAULT_MAX_RECORDS


def test_model_polling_after_logger_rollover(app):
    from core.logger import Logger

    logger = Logger(max_records=3)
    model = LogModel(max_records=3)

    for i in range(5):
        logger.info(f"m{i}")

    model.append_records(logger.poll(0))
    assert [model.record_at(i).message for i in range(model.rowCount())] == ["m2", "m3", "m4"]

    cursor = logger.last_seq
    logger.info("m5")
    logger.info("m6")
    model.append_records(logger.poll(cursor))

    assert model.rowCount() == 3
    messages = [model.record_at(i).message for i in range(model.rowCount())]
    assert messages == ["m4", "m5", "m6"]
    assert len(messages) == len(set(messages))

def test_model_mirrors_logger_with_critical_eviction(app):
    from core.logger import Logger

    logger = Logger(max_records=3)
    model = LogModel(max_records=3)

    logger.error("e_old")
    logger.debug("d1")
    logger.debug("d2")

    result = logger.drain(0)
    model.replace_records(result.records)
    assert [model.record_at(i).message for i in range(model.rowCount())] == ["e_old", "d1", "d2"]

    cursor = logger.last_seq
    logger.error("e_new")
    result = logger.drain(cursor)

    model.remove_by_seqs(result.evicted_seqs)
    model.append_records(result.records)

    assert [model.record_at(i).message for i in range(model.rowCount())] == ["e_old", "d2", "e_new"]
    assert [model.record_at(i).message for i in range(model.rowCount())] == [
        r.message for r in logger.poll(0)
    ]

def test_model_record_exposes_nodes(app):
    model = LogModel(max_records=3)
    records = make_records(1)
    records[0] = LogRecord(
        seq=records[0].seq,
        ts=records[0].ts,
        level=records[0].level,
        source=records[0].source,
        context=records[0].context,
        message=records[0].message,
        nodes=("pSphere1", "pSphere2"),
    )
    model.append_records(records)

    assert model.record_at(0).nodes == ("pSphere1", "pSphere2")


def test_model_tooltip_contains_nodes(app):
    model = LogModel(max_records=3)
    records = make_records(1)
    records[0] = LogRecord(
        seq=records[0].seq,
        ts=records[0].ts,
        level=records[0].level,
        source=records[0].source,
        context=records[0].context,
        message=records[0].message,
        nodes=("pSphere1",),
    )
    model.append_records(records)

    index = model.index(0, 0)
    tooltip = model.data(index, QtCore.Qt.ToolTipRole)
    assert "Nodes: pSphere1" in tooltip


def test_proxy_maps_filtered_row_to_source_record(app):
    model = LogModel(max_records=5)
    model.append_records(make_records(3))

    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_source("test")  # all make_records use source="test"; filter by text instead
    proxy.set_source("")
    proxy.set_text("m1")

    assert proxy.rowCount() == 1
    src = proxy.mapToSource(proxy.index(0, 0))
    assert src.row() == 1
    assert model.record_at(src.row()).message == "m1"


def test_log_viewer_select_nodes_calls_cmds_select(app, monkeypatch):
    from core.logger import Logger
    from ui import log_panel

    viewer = log_panel.LogViewer(Logger())
    calls = []
    monkeypatch.setattr(
        log_panel.cmds,
        "select",
        lambda nodes, replace=True, noExpand=True: calls.append((list(nodes), replace, noExpand)),
    )

    viewer._select_record_nodes(["pSphere1", "pSphere2"])

    assert calls == [(["pSphere1", "pSphere2"], True, True)]
    viewer.deleteLater()


def test_model_mirror_preserves_nodes_after_drain(app):
    from core.logger import Logger

    logger = Logger(max_records=3)
    model = LogModel(max_records=3)

    logger.error("e_old", nodes=["pSphere1"])
    logger.debug("d1", nodes=["pSphere2"])
    logger.debug("d2", nodes=["pSphere3"])

    result = logger.drain(0)
    model.replace_records(result.records)

    cursor = logger.last_seq
    logger.error("e_new", nodes=["pSphere4"])
    result = logger.drain(cursor)
    model.remove_by_seqs(result.evicted_seqs)
    model.append_records(result.records)

    assert [model.record_at(i).nodes for i in range(model.rowCount())] == [
        ("pSphere1",), ("pSphere3",), ("pSphere4",)
    ]

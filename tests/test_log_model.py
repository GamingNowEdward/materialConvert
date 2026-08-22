import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core.logger import DEFAULT_MAX_RECORDS, LogLevel, LogRecord
from ui import QtWidgets
from ui.log_panel import LogModel


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

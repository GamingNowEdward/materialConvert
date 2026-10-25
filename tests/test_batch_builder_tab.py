"""Batch Builder table: status colours and the legend under the table."""

import pytest

from core.builder_context import BuilderContext
from core.logger import Logger
from ui import QtCore, QtWidgets
from ui.tabs import batch_builder_tab as tab_module
from ui.tabs.batch_builder_tab import BatchBuilderTab


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _tab(qapp):
    ctx = BuilderContext(logger=Logger())
    tab = BatchBuilderTab(ctx, logger=Logger())
    # keep the Qt widget alive for the duration of the test
    tab._widget = tab.build_ui()
    return tab


def _scan_result():
    return {
        "materials": [{
            "name": "rock",
            "channels": {
                "baseColor": {"channel": "BaseColor", "path": "C:/t/rock_COL.png",
                              "options": {}},
                "normal_bump": {"channel": "Normal", "path": "C:/t/rock_NRM16.png",
                                "options": {}},
            },
        }],
        "unparsed": ["C:/t/rock_Preview.png"],
        "conflicts": [{
            "material": "rock",
            "common_attr": "normal_bump",
            "existing": "C:/t/rock_NRM16.png",
            "kept": "C:/t/rock_NRM16.png",
            "candidates": ["C:/t/rock_NRM16.png", "C:/t/rock_NRM.png"],
            "dropped": ["C:/t/rock_NRM.png"],
        }],
        "conflict_materials": ["rock"],
    }


def _background(item):
    return item.background().color().name().lower()


def test_status_rows_are_coloured_by_severity(qapp):
    tab = _tab(qapp)
    tab.scan_result = _scan_result()

    tab._populate_table()

    rows = {}
    for row in range(tab.table.rowCount()):
        status = tab.table.item(row, 3).text()
        rows.setdefault(status, []).append(row)

    # an OK row is not painted at all
    ok_row = rows["OK"][0]
    assert tab.table.item(ok_row, 0).background().style() == QtCore.Qt.NoBrush

    kept_row = rows["CONFLICT (kept)"][0]
    assert _background(tab.table.item(kept_row, 0)) == tab_module._KEPT_CONFLICT_BG

    dropped_row = rows["CONFLICT"][0]
    assert _background(tab.table.item(dropped_row, 0)) == tab_module._DROPPED_CONFLICT_BG

    unparsed_row = rows["UNPARSED"][0]
    assert _background(tab.table.item(unparsed_row, 0)) == tab_module._UNPARSED_BG

    # the three problem states are visually distinct
    assert len({tab_module._KEPT_CONFLICT_BG, tab_module._DROPPED_CONFLICT_BG,
                tab_module._UNPARSED_BG}) == 3


def test_table_legend_explains_the_statuses(qapp):
    tab = _tab(qapp)

    legend = tab.table_legend.text()

    assert "CONFLICT (kept)" in legend
    assert "UNPARSED" in legend

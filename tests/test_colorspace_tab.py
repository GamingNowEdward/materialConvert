import pytest

import core.colorspace as cs
from core.logger import Logger
from ui import QtWidgets
from ui.tabs.colorspace_tab import ColorspaceTab


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _mock_maya(monkeypatch, set_attr_calls, paths=None, nodes=("file1",),
               channels=None):
    paths = paths or {}
    channels = channels or {}

    def get_attr(plug, **kwargs):
        node = plug.split(".")[0]
        if plug.endswith(".fileTextureName"):
            return paths.get(node, "")
        if plug.endswith(".colorSpace"):
            return "Raw"
        return ""

    monkeypatch.setattr(cs.cmds, "ls", lambda **kwargs: list(nodes))
    monkeypatch.setattr(cs.cmds, "getAttr", get_attr)
    monkeypatch.setattr(cs.cmds, "setAttr", lambda *a, **k: set_attr_calls.append(a))
    monkeypatch.setattr(
        cs.cmds, "colorManagementPrefs",
        lambda q=False, **kwargs: ["Utility - sRGB - Texture", "Utility - Raw"],
    )
    monkeypatch.setattr(cs.cmds, "listNodeTypes", lambda *a, **k: ["aiStandardSurface"])
    monkeypatch.setattr(cs.cmds, "nodeType", lambda node: "transform")
    monkeypatch.setattr(
        cs.cmds, "listConnections", lambda node, **kwargs: channels.get(node, [])
    )


def test_colorspace_tab_builds(qapp):
    tab = ColorspaceTab(logger=Logger())
    widget = tab.build_ui()
    assert widget is not None


def test_refresh_pops_table_without_set_attr(qapp, monkeypatch):
    set_attr_calls = []
    _mock_maya(monkeypatch, set_attr_calls, paths={"file1": "C:/t_baseColor.png"})

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    assert tab.table.rowCount() == 1
    assert set_attr_calls == []

    assert tab.table.item(0, 0).text() == "file1"
    assert tab.table.item(0, 1).text() == "C:/t_baseColor.png"
    assert tab.table.item(0, 2).text() == "Raw"
    assert tab.table.item(0, 3).text() == "Utility - sRGB - Texture"
    assert tab.table.item(0, 4).text().startswith("MATCHED")


def _row_for_node(tab, node):
    for row in range(tab.table.rowCount()):
        if tab.table.item(row, 0).text() == node:
            return row
    raise AssertionError(f"row for node {node} not found")


def test_apply_selected_only_matched(qapp, monkeypatch):
    set_attr_calls = []
    _mock_maya(
        monkeypatch,
        set_attr_calls,
        paths={"file1": "C:/t_baseColor.png", "file2": "C:/t_untitled.png"},
        nodes=("file1", "file2"),
    )

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    tab.table.selectRow(_row_for_node(tab, "file1"))
    tab._apply_selected()
    assert [c[0] for c in set_attr_calls] == ["file1.colorSpace"]
    assert set_attr_calls[-1][1] == "Utility - sRGB - Texture"

    tab.table.selectRow(_row_for_node(tab, "file2"))
    tab._apply_selected()
    # unmatched row must not be silently applied
    assert [c[0] for c in set_attr_calls] == ["file1.colorSpace"]


def test_apply_all_matched_only_matched(qapp, monkeypatch):
    set_attr_calls = []
    _mock_maya(
        monkeypatch,
        set_attr_calls,
        paths={"file1": "C:/t_baseColor.png", "file2": "C:/t_untitled.png"},
        nodes=("file1", "file2"),
    )

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    tab._apply_all_matched()
    assert [c[0] for c in set_attr_calls] == ["file1.colorSpace"]


def test_manual_assignment_applies_to_selected(qapp, monkeypatch):
    set_attr_calls = []
    _mock_maya(monkeypatch, set_attr_calls, paths={"file1": "C:/t_baseColor.png"})

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    tab.table.selectRow(0)
    tab.manual_combo.setCurrentText("Utility - Raw")
    tab._apply_manual()

    assert [c[0] for c in set_attr_calls] == ["file1.colorSpace"]
    assert set_attr_calls[-1][1] == "Utility - Raw"


def test_apply_manual_requires_selection(qapp, monkeypatch):
    set_attr_calls = []
    _mock_maya(monkeypatch, set_attr_calls, paths={"file1": "C:/t_baseColor.png"})

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    tab._apply_manual()
    assert set_attr_calls == []


def test_row_selection_syncs_maya(qapp, monkeypatch):
    set_attr_calls = []
    select_calls = []
    _mock_maya(monkeypatch, set_attr_calls, paths={"file1": "C:/t_baseColor.png"})
    monkeypatch.setattr(cs.cmds, "select", lambda *a, **k: select_calls.append(a))

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    tab.table.selectRow(0)
    assert select_calls == [(["file1"],)]

    tab.table.clearSelection()
    assert select_calls == [(["file1"],), ()]


def test_refresh_does_not_sync_selection(qapp, monkeypatch):
    set_attr_calls = []
    select_calls = []
    _mock_maya(monkeypatch, set_attr_calls, paths={"file1": "C:/t_baseColor.png"})
    monkeypatch.setattr(cs.cmds, "select", lambda *a, **k: select_calls.append(a))

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._refresh()

    # populating the table must not touch the Maya selection
    assert select_calls == []


def test_ignore_color_space_rules_sets_all_files(qapp, monkeypatch):
    set_attr_calls = []
    select_calls = []
    _mock_maya(monkeypatch, set_attr_calls, paths={"file1": "C:/t_baseColor.png"},
               nodes=("file1", "file2"))
    monkeypatch.setattr(cs.cmds, "select", lambda *a, **k: select_calls.append(a))

    tab = ColorspaceTab(logger=Logger())
    tab.build_ui()
    tab._ignore_color_space_rules()

    assert [c[0] for c in set_attr_calls] == [
        "file1.ignoreColorSpaceFileRules", "file2.ignoreColorSpaceFileRules"
    ]
    assert select_calls == [(["file1", "file2"],)]


def test_node_tools_has_no_colorspace_ui(qapp):
    from ui.tabs import node_tools_tab as ntt

    tab = ntt.NodeToolsTab(ctx=object(), logger=Logger())
    for attr in (
        "_auto_match_color_space", "_apply_color_space", "_match_by_filename",
        "_match_by_channel", "_trace_channel_targets", "_set_color_space",
        "_get_available_color_spaces", "_ignore_color_space_rules",
    ):
        assert not hasattr(tab, attr), f"{attr} should be removed from NodeToolsTab"

    widget = tab.build_ui()
    labels = [btn.text() for btn in widget.findChildren(QtWidgets.QPushButton)]
    for forbidden in ("Color Space", "Auto Match", "ignoreColorSpaceFileRules"):
        assert not any(forbidden in label for label in labels), (
            f"Node Tools still exposes colorspace UI: {forbidden}"
        )


def test_node_tools_accepts_injected_config(qapp):
    from core.config_loader import ConfigLoader
    from ui.tabs import node_tools_tab as ntt

    loader = ConfigLoader()
    tab = ntt.NodeToolsTab(ctx=object(), logger=Logger(), config=loader)
    assert tab.config is loader

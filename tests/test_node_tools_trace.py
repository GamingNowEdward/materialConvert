from core.logger import Logger, LogLevel
from ui.tabs import node_tools_tab as ntt


def test_trace_skips_place2d_without_warnings(monkeypatch):
    log = Logger()
    tab = ntt.NodeToolsTab(ctx=object(), logger=log)

    def node_type(node):
        if node.startswith("aiStandardSurface"):
            return "aiStandardSurface"
        if node.startswith("place2dTexture"):
            return "place2dTexture"
        return "transform"

    def list_connections(node, **kwargs):
        if node == "file1":
            return ["place2dTexture225.outUV", "aiStandardSurface1.baseColor"]
        return []

    monkeypatch.setattr(ntt.cmds, "listNodeTypes", lambda *a, **k: ["aiStandardSurface"])
    monkeypatch.setattr(ntt.cmds, "nodeType", node_type)
    monkeypatch.setattr(ntt.cmds, "listConnections", list_connections)

    targets = tab._trace_channel_targets("file1")

    assert targets == ["baseColor"]
    assert [r for r in log.poll(0) if r.level == LogLevel.WARN] == []


def test_trace_budget_emits_single_warning(monkeypatch):
    log = Logger()
    tab = ntt.NodeToolsTab(ctx=object(), logger=log)
    tab._TRACE_NODE_BUDGET = 2

    calls = []

    def list_connections(node, **kwargs):
        calls.append(node)
        if node == "file1":
            return ["n0.out"]
        idx = int(node[1:])
        return [f"n{idx + 1}.out"]

    monkeypatch.setattr(ntt.cmds, "listNodeTypes", lambda *a, **k: ["aiStandardSurface"])
    monkeypatch.setattr(ntt.cmds, "nodeType", lambda node: "transform")
    monkeypatch.setattr(ntt.cmds, "listConnections", list_connections)

    targets = tab._trace_channel_targets("file1", max_depth=10)

    assert targets == []
    warnings = [r.message for r in log.poll(0) if r.level == LogLevel.WARN]
    assert any("budget exceeded" in message for message in warnings)
    assert len(calls) <= tab._TRACE_NODE_BUDGET + 3

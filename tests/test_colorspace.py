import core.colorspace as cs
from core.colorspace import (
    ChannelDriver,
    ColorSpaceMatcher,
    ColorSpaceResolver,
    DriverStatus,
    MatchState,
    NameDriver,
)
from core.logger import Logger, LogLevel


def _name_driver():
    return NameDriver(logger=Logger())


def test_name_driver_match_srgb():
    res = _name_driver().match(r"C:/tex/hero_baseColor.png")
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["srgb"]


def test_name_driver_match_raw():
    res = _name_driver().match(r"C:/tex/hero_normal.png")
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["raw"]


def test_name_driver_no_match():
    res = _name_driver().match(r"C:/tex/untitled.dds")
    assert res.status == DriverStatus.NO_MATCH
    assert res.roles == []


def test_name_driver_empty_path():
    assert _name_driver().match("").status == DriverStatus.NO_MATCH
    assert _name_driver().match("C:/tex/").status == DriverStatus.NO_MATCH


def test_name_driver_normalizes_separators_and_case():
    res = _name_driver().match(r"X:/Foo-Base_Color.PNG")
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["srgb"]


def test_name_driver_ambiguous_multiple_roles():
    res = _name_driver().match("hero_basecolor_normal.png")
    assert res.status == DriverStatus.AMBIGUOUS
    assert set(res.roles) == {"srgb", "raw"}


def _channel_driver(monkeypatch, shader_types=("aiStandardSurface",)):
    log = Logger()
    driver = ChannelDriver(logger=log)
    monkeypatch.setattr(cs.cmds, "listNodeTypes", lambda *a, **k: list(shader_types))
    return driver, log


def test_trace_skips_place2d_without_warnings(monkeypatch):
    driver, log = _channel_driver(monkeypatch)

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

    monkeypatch.setattr(cs.cmds, "nodeType", node_type)
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    targets = driver.trace_channel_targets("file1")

    assert targets == ["baseColor"]
    assert [r for r in log.poll(0) if r.level == LogLevel.WARN] == []


def test_trace_budget_emits_single_warning(monkeypatch):
    driver, log = _channel_driver(monkeypatch)
    driver._TRACE_NODE_BUDGET = 2

    calls = []

    def list_connections(node, **kwargs):
        calls.append(node)
        if node == "file1":
            return ["n0.out"]
        idx = int(node[1:])
        return [f"n{idx + 1}.out"]

    monkeypatch.setattr(cs.cmds, "nodeType", lambda node: "transform")
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    targets = driver.trace_channel_targets("file1", max_depth=10)

    assert targets == []
    warnings = [r.message for r in log.poll(0) if r.level == LogLevel.WARN]
    assert any("budget exceeded" in message for message in warnings)
    assert len(calls) <= driver._TRACE_NODE_BUDGET + 3


def test_channel_match_single(monkeypatch):
    driver, _ = _channel_driver(monkeypatch)

    def node_type(node):
        return "aiStandardSurface" if node.startswith("aiStandardSurface") else "transform"

    def list_connections(node, **kwargs):
        if node == "file1":
            return ["aiStandardSurface1.baseColor"]
        return []

    monkeypatch.setattr(cs.cmds, "nodeType", node_type)
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    res = driver.match("file1")
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["srgb"]


def test_channel_match_consistent_channels(monkeypatch):
    driver, _ = _channel_driver(monkeypatch)

    def node_type(node):
        return "aiStandardSurface" if node.startswith("aiStandardSurface") else "transform"

    def list_connections(node, **kwargs):
        if node == "file1":
            return ["aiStandardSurface1.baseColor", "aiStandardSurface1.specularColor"]
        return []

    monkeypatch.setattr(cs.cmds, "nodeType", node_type)
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    res = driver.match("file1")
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["srgb"]


def test_channel_match_conflicting_channels(monkeypatch):
    driver, _ = _channel_driver(monkeypatch)

    def node_type(node):
        return "aiStandardSurface" if node.startswith("aiStandardSurface") else "transform"

    def list_connections(node, **kwargs):
        if node == "file1":
            return ["aiStandardSurface1.baseColor", "aiStandardSurface1.roughness"]
        return []

    monkeypatch.setattr(cs.cmds, "nodeType", node_type)
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    res = driver.match("file1")
    assert res.status == DriverStatus.AMBIGUOUS
    assert set(res.roles) == {"srgb", "raw"}


def test_channel_match_no_channel(monkeypatch):
    driver, _ = _channel_driver(monkeypatch)

    monkeypatch.setattr(cs.cmds, "nodeType", lambda node: "transform")
    monkeypatch.setattr(cs.cmds, "listConnections", lambda node, **kwargs: [])

    res = driver.match("file1")
    assert res.status == DriverStatus.NO_MATCH
    assert res.roles == []


def test_channel_trace_depth_limit(monkeypatch):
    driver, _ = _channel_driver(monkeypatch)

    def node_type(node):
        return "aiStandardSurface" if node.startswith("mat") else "transform"

    def list_connections(node, **kwargs):
        return {
            "file1": ["a1.out"],
            "a1": ["b1.out"],
            "b1": ["c1.out"],
            "c1": ["d1.out"],
            "d1": ["mat1.baseColor"],
        }.get(node, [])

    monkeypatch.setattr(cs.cmds, "nodeType", node_type)
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    # material sits at depth 5; default max_depth=4 must not reach it
    assert driver.match("file1").status == DriverStatus.NO_MATCH
    # a deeper budget reaches it
    assert driver.trace_channel_targets("file1", max_depth=8) == ["baseColor"]


def _matcher(monkeypatch, available=("Utility - sRGB - Texture", "Utility - Raw"),
             paths=None, colorspaces=None, connections=None,
             shader_types=("aiStandardSurface",)):
    log = Logger()
    matcher = ColorSpaceMatcher(logger=log)
    paths = paths or {}
    colorspaces = colorspaces or {}
    connections = connections or {}

    def get_attr(plug, **kwargs):
        node = plug.split(".")[0]
        if plug.endswith(".fileTextureName"):
            return paths.get(node, "")
        if plug.endswith(".colorSpace"):
            return colorspaces.get(node, "Raw")
        raise KeyError(plug)

    def node_type(node):
        return "aiStandardSurface" if node.startswith("ai") else "transform"

    monkeypatch.setattr(cs.cmds, "getAttr", get_attr)
    monkeypatch.setattr(
        cs.cmds, "colorManagementPrefs", lambda q=False, **kwargs: list(available)
    )
    monkeypatch.setattr(cs.cmds, "listNodeTypes", lambda *a, **k: list(shader_types))
    monkeypatch.setattr(cs.cmds, "nodeType", node_type)
    monkeypatch.setattr(cs.cmds, "listConnections", lambda node, **kwargs: connections.get(node, []))
    return matcher


def test_matcher_name_only_match(monkeypatch):
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_baseColor.png"})
    res = matcher.match("file1")
    assert res.state == MatchState.MATCHED
    assert res.file_node == "file1"
    assert res.file_path == "C:/t_baseColor.png"
    assert res.actual_colorspace == "Raw"
    assert res.prematch_colorspace == "Utility - sRGB - Texture"


def test_matcher_channel_only_match(monkeypatch):
    matcher = _matcher(
        monkeypatch,
        paths={"file1": "C:/t_untitled.png"},
        connections={"file1": ["aiStd1.baseColor"]},
    )
    res = matcher.match("file1")
    assert res.state == MatchState.MATCHED
    assert res.prematch_colorspace == "Utility - sRGB - Texture"


def test_matcher_name_and_channel_consistent(monkeypatch):
    matcher = _matcher(
        monkeypatch,
        paths={"file1": "C:/t_baseColor.png"},
        connections={"file1": ["aiStd1.baseColor"]},
    )
    res = matcher.match("file1")
    assert res.state == MatchState.MATCHED
    assert res.prematch_colorspace == "Utility - sRGB - Texture"


def test_matcher_conflict(monkeypatch):
    matcher = _matcher(
        monkeypatch,
        paths={"file1": "C:/t_baseColor.png"},
        connections={"file1": ["aiStd1.roughness"]},
    )
    res = matcher.match("file1")
    assert res.state == MatchState.CONFLICT
    assert res.prematch_colorspace == ""
    assert "filename -> srgb" in res.diagnostic


def test_matcher_name_ambiguous(monkeypatch):
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_basecolor_normal.png"})
    res = matcher.match("file1")
    assert res.state == MatchState.AMBIGUOUS
    assert res.prematch_colorspace == ""


def test_matcher_channel_ambiguous(monkeypatch):
    matcher = _matcher(
        monkeypatch,
        paths={"file1": "C:/t_untitled.png"},
        connections={"file1": ["aiStd1.baseColor", "aiStd1.roughness"]},
    )
    res = matcher.match("file1")
    assert res.state == MatchState.AMBIGUOUS


def test_matcher_unmatched(monkeypatch):
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_untitled.png"})
    res = matcher.match("file1")
    assert res.state == MatchState.UNMATCHED
    assert res.prematch_colorspace == ""


def test_matcher_invalid_role_unresolvable(monkeypatch):
    matcher = _matcher(
        monkeypatch,
        available=("Utility - sRGB - Texture",),
        paths={"file1": "C:/t_normal.png"},
    )
    res = matcher.match("file1")
    assert res.state == MatchState.INVALID
    assert res.prematch_colorspace == ""
    assert "could not be resolved" in res.diagnostic


def test_matcher_resolves_role_to_actual(monkeypatch):
    matcher = _matcher(
        monkeypatch,
        available=("Raw", "Utility - sRGB - Texture"),
        paths={"file1": "C:/t_normal.png"},
    )
    res = matcher.match("file1")
    assert res.state == MatchState.MATCHED
    assert res.prematch_colorspace == "Raw"


def test_resolver_caches_available_spaces(monkeypatch):
    calls = []

    def cm_prefs(q=False, **kwargs):
        calls.append(1)
        return ["Raw", "Utility - sRGB - Texture"]

    monkeypatch.setattr(cs.cmds, "colorManagementPrefs", cm_prefs)
    resolver = ColorSpaceResolver(logger=Logger())
    assert resolver.resolve("raw") == "Raw"
    assert resolver.resolve("raw") == "Raw"
    assert len(calls) == 1
    resolver.reset()
    assert resolver.resolve("raw") == "Raw"
    assert len(calls) == 2


def test_matcher_reads_errors_into_diagnostic(monkeypatch):
    matcher = _matcher(monkeypatch, paths={})

    def get_attr(plug, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cs.cmds, "getAttr", get_attr)

    res = matcher.match("file1")
    assert res.state == MatchState.UNMATCHED
    assert "error reading file path" in res.diagnostic
    assert "error reading colorSpace" in res.diagnostic
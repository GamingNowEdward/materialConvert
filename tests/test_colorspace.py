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


def test_name_driver_matches_short_aliases_at_the_end_of_a_filename():
    """A short alias right before the extension must still match (stem matching)."""
    driver = _name_driver()

    assert driver.match(r"C:/tex/rock_col.jpg").roles == ["srgb"]
    assert driver.match(r"C:/tex/rock_dif.png").roles == ["srgb"]
    assert driver.match(r"C:/tex/rock_nrm.tif").roles == ["raw"]
    assert driver.match(r"C:/tex/rock_sss.exr").roles == ["srgb"]


def test_name_driver_short_suffix_only_when_enabled():
    driver = _name_driver()

    assert driver.match(r"C:/tex/rock_d.jpg").status == DriverStatus.NO_MATCH

    res = driver.match(r"C:/tex/rock_d.jpg", enable_short_suffixes=True)
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["srgb"]


def test_name_driver_empty_path():
    assert _name_driver().match("").status == DriverStatus.NO_MATCH
    assert _name_driver().match("C:/tex/").status == DriverStatus.NO_MATCH


def test_name_driver_ignores_requested_aliases():
    """A set-wide alias is not evidence about one file."""
    driver = _name_driver()
    path = "C:/tex/FabricCottonMuslin004_COL_2K_METALNESS.png"

    # both a color channel (col) and a data channel (metalness) match
    assert driver.match(path).status == DriverStatus.AMBIGUOUS
    assert driver.match(path).roles == ["raw", "srgb"]

    res = driver.match(path, ignore_aliases={"metalness"})
    assert res.status == DriverStatus.MATCH
    assert res.roles == ["srgb"]


def test_name_driver_matches_short_aliases_as_tokens():
    driver = _name_driver()

    assert driver.match("C:/tex/rock_COL_2K.png").roles == ["srgb"]
    assert driver.match("C:/tex/rock_SSS_2K.png").roles == ["srgb"]
    assert driver.match("C:/tex/rock_NRM16_2K.png").roles == ["raw"]
    assert driver.match("C:/tex/rock_MASK_2K.png").roles == ["raw"]
    # still token-bounded: a short alias must not match inside a word
    assert driver.match("C:/tex/school.png").status == DriverStatus.NO_MATCH


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


def _match_result(node, state, prematch=""):
    return cs.MatchResult(
        file_node=node,
        file_path=f"C:/{node}.png",
        actual_colorspace="Raw",
        name_driver_result=cs.NameDriverResult(),
        channel_driver_result=cs.ChannelDriverResult(),
        prematch_colorspace=prematch,
        state=state,
        diagnostic="",
    )


def test_apply_matched_applies_only_matched_results(monkeypatch):
    set_attr_calls = []
    monkeypatch.setattr(cs.cmds, "setAttr", lambda *a, **k: set_attr_calls.append(a))
    monkeypatch.setattr(cs.cmds, "undoInfo", lambda **k: None)

    matcher = ColorSpaceMatcher(logger=Logger())
    outcome = matcher.apply_matched([
        _match_result("file1", MatchState.MATCHED, "Utility - sRGB - Texture"),
        _match_result("file2", MatchState.CONFLICT),
        _match_result("file3", MatchState.UNMATCHED),
    ])

    assert [c[0] for c in set_attr_calls] == ["file1.colorSpace"]
    assert set_attr_calls[0][1] == "Utility - sRGB - Texture"
    assert outcome["applied"] == [("file1", "Utility - sRGB - Texture")]
    assert outcome["skipped"] == 2
    assert outcome["failed"] == []


def test_apply_matched_reports_failures(monkeypatch):
    log = Logger()

    def set_attr(plug, *args, **kwargs):
        raise RuntimeError("read only")

    monkeypatch.setattr(cs.cmds, "setAttr", set_attr)
    monkeypatch.setattr(cs.cmds, "undoInfo", lambda **k: None)

    matcher = ColorSpaceMatcher(logger=log)
    outcome = matcher.apply_matched([
        _match_result("file1", MatchState.MATCHED, "Raw"),
    ])

    assert outcome["applied"] == []
    assert len(outcome["failed"]) == 1
    assert any(r.level == LogLevel.WARN for r in log.poll(0))
# --------------------------------------------------------------------------- #
# Evidence completeness / stale revalidation
# --------------------------------------------------------------------------- #

def test_name_driver_requires_token_boundaries():
    driver = _name_driver()
    # a keyword inside a longer word must not match (old substring behaviour did)
    assert driver.match("C:/tex/hero_roughnessblur.png").status == DriverStatus.NO_MATCH
    assert driver.match("C:/tex/hero_roughness.png").status == DriverStatus.MATCH


def test_channel_driver_marks_depth_truncation_incomplete(monkeypatch):
    driver, _log = _channel_driver(monkeypatch)
    connections = {
        "file1": ["aiStandardSurface1.baseColor", "a1.out"],
        "a1": ["a2.out"],
        "a2": ["a3.out"],
        "a3": ["a4.out"],
        "a4": ["aiStandardSurface1.specularColor"],
    }
    monkeypatch.setattr(cs.cmds, "nodeType",
                        lambda node: "aiStandardSurface" if node.startswith("ai") else "transform")
    monkeypatch.setattr(cs.cmds, "listConnections",
                        lambda node, **kwargs: connections.get(node, []))

    res = driver.trace_channel_targets("file1")

    assert res.targets == ["baseColor"]
    assert res.complete is False
    assert res.depth_limited is True
    assert res.truncated is False


def test_channel_driver_marks_budget_truncation_incomplete(monkeypatch):
    driver, _log = _channel_driver(monkeypatch)
    driver._TRACE_NODE_BUDGET = 2

    def list_connections(node, **kwargs):
        if node == "file1":
            return ["n0.out"]
        return ["n%d.out" % (int(node[1:]) + 1)]

    monkeypatch.setattr(cs.cmds, "nodeType", lambda node: "transform")
    monkeypatch.setattr(cs.cmds, "listConnections", list_connections)

    result = driver.match("file1")

    assert result.truncated is True
    assert result.evidence_complete is False


def test_channel_match_on_incomplete_evidence_is_ambiguous(monkeypatch):
    connections = {
        "file1": ["aiStd1.baseColor", "a1.out"],
        "a1": ["a2.out"],
        "a2": ["a3.out"],
        "a3": ["a4.out"],
        "a4": ["aiStd1.specularColor"],
    }
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_untitled.png"},
                       connections=connections)

    res = matcher.match("file1")

    assert res.state == MatchState.AMBIGUOUS
    assert res.prematch_colorspace == ""
    assert "incomplete evidence" in res.diagnostic
    assert res.evidence_complete is False


def test_complete_filename_evidence_still_matches(monkeypatch):
    connections = {
        "file1": ["aiStd1.baseColor", "a1.out"],
        "a1": ["a2.out"],
        "a2": ["a3.out"],
        "a3": ["a4.out"],
        "a4": ["aiStd1.specularColor"],
    }
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_baseColor.png"},
                       connections=connections)

    res = matcher.match("file1")

    # the filename is independent, complete evidence
    assert res.state == MatchState.MATCHED
    assert res.evidence_complete is False


def test_unmatched_with_incomplete_trace_says_so(monkeypatch):
    connections = {
        "file1": ["a1.out"],
        "a1": ["a2.out"],
        "a2": ["a3.out"],
        "a3": ["a4.out"],
        "a4": ["aiStd1.baseColor"],
    }
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_untitled.png"},
                       connections=connections)

    res = matcher.match("file1")

    assert res.state == MatchState.UNMATCHED
    assert "not exhaustive" in res.diagnostic


def test_apply_matched_revalidation_skips_stale(monkeypatch):
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_baseColor.png"})
    set_attr_calls = []
    monkeypatch.setattr(cs.cmds, "setAttr", lambda *a, **k: set_attr_calls.append(a))
    monkeypatch.setattr(cs.cmds, "undoInfo", lambda **k: None)

    stale_result = _match_result("file1", MatchState.MATCHED, "Utility - Raw")
    outcome = matcher.apply_matched([stale_result], revalidate=True)

    assert outcome["applied"] == []
    assert outcome["stale"] == ["file1"]
    assert set_attr_calls == []


def test_apply_matched_revalidation_applies_fresh_result(monkeypatch):
    matcher = _matcher(monkeypatch, paths={"file1": "C:/t_baseColor.png"})
    set_attr_calls = []
    monkeypatch.setattr(cs.cmds, "setAttr", lambda *a, **k: set_attr_calls.append(a))
    monkeypatch.setattr(cs.cmds, "undoInfo", lambda **k: None)

    fresh_result = _match_result("file1", MatchState.MATCHED,
                                 "Utility - sRGB - Texture")
    outcome = matcher.apply_matched([fresh_result], revalidate=True)

    assert outcome["stale"] == []
    assert outcome["applied"] == [("file1", "Utility - sRGB - Texture")]


# --------------------------------------------------------------------------- #
# Set-wide filename keywords (a suffix every file of the set shares)
# --------------------------------------------------------------------------- #

_SET_DIR = "C:/tex/FabricCottonMuslin004/"
_SET_PATHS = {
    "file_col": _SET_DIR + "FabricCottonMuslin004_COL_2K_METALNESS.png",
    "file_disp": _SET_DIR + "FabricCottonMuslin004_DISP16_2K_METALNESS.png",
    "file_mask": _SET_DIR + "FabricCottonMuslin004_MASK_2K_METALNESS.png",
    "file_nrm": _SET_DIR + "FabricCottonMuslin004_NRM16_2K_METALNESS.png",
    "file_rough": _SET_DIR + "FabricCottonMuslin004_ROUGHNESS_2K_METALNESS.png",
    "file_sss": _SET_DIR + "FabricCottonMuslin004_SSS_2K_METALNESS.png",
}
_SET_CONNECTIONS = {
    "file_col": ["aiStd1.baseColor"],
    "file_sss": ["aiStd1.subsurfaceColor"],
    "file_rough": ["aiStd1.specularRoughness"],
    "file_nrm": ["aiStd1.normalCamera"],
    "file_disp": ["aiStd1.displacement"],
    "file_mask": ["aiStd1.opacity"],
}


def _scan_matcher(monkeypatch, paths, connections):
    matcher = _matcher(monkeypatch, paths=paths, connections=connections)
    monkeypatch.setattr(cs.cmds, "ls", lambda **kwargs: list(paths))
    return matcher


def test_scan_ignores_set_wide_filename_keywords(monkeypatch):
    """`_METALNESS` on every file of a set is not evidence about one file."""
    matcher = _scan_matcher(monkeypatch, _SET_PATHS, _SET_CONNECTIONS)

    results = {result.file_node: result for result in matcher.scan()}

    assert all(result.state == MatchState.MATCHED for result in results.values())

    # the two color channels are now decided by the filename and the channel
    # evidence, which agree
    for node in ("file_col", "file_sss"):
        assert results[node].name_driver_result.status == DriverStatus.MATCH
        assert results[node].name_driver_result.roles == ["srgb"]
        assert results[node].prematch_colorspace == "Utility - sRGB - Texture"

    for node in ("file_disp", "file_mask", "file_nrm", "file_rough"):
        assert results[node].prematch_colorspace == "Utility - Raw"


def test_scan_falls_back_when_only_common_keywords_remain(monkeypatch):
    """Ignoring the common keyword would resolve nothing, so it is used after all."""
    paths = {
        "file_a": "C:/tex/rockA_METALNESS.png",
        "file_b": "C:/tex/rockB_METALNESS.png",
        "file_c": "C:/tex/rockC_METALNESS.png",
    }
    matcher = _scan_matcher(monkeypatch, paths, {})

    results = {result.file_node: result for result in matcher.scan()}

    assert all(result.state == MatchState.MATCHED for result in results.values())
    assert all(result.name_driver_result.status == DriverStatus.MATCH
               for result in results.values())
    assert all(result.prematch_colorspace == "Utility - Raw"
               for result in results.values())


def test_scan_keeps_name_evidence_for_unrelated_sets(monkeypatch):
    """Only the directory's own shared keywords are ignored."""
    paths = {
        "file_wood": "C:/tex/wood/wood_basecolor.png",
        "file_metal": "C:/tex/wood/wood_metalness.png",
    }
    matcher = _scan_matcher(monkeypatch, paths, {})

    results = {result.file_node: result for result in matcher.scan()}

    # two files is too few for a "shared" keyword, so both stay name-matched
    assert results["file_wood"].prematch_colorspace == "Utility - sRGB - Texture"
    assert results["file_metal"].prematch_colorspace == "Utility - Raw"

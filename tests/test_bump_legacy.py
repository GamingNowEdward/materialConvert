"""Unit tests for legacy-normal file materialization.

Covers the two gaps: a missing place2dTexture must fail the conversion, and a
materialized ``file`` node may only be reused when its UV chain is complete and
its ownership is unambiguous.
"""

import types

from core.converters import bump as bump_module
from core.converters.bump import BumpConverter
from core.logger import Logger
from core.node_utils import P2D_CONNECTIONS

_MARKER = "mcEmbeddedSource"


class FakeBumpCmds:
    def __init__(self):
        self.files = []
        self.paths = {}
        self.markers = {}
        self.uv_upstream = {}
        self.node_types = {}
        self.connected = set()
        self.connect_calls = []
        self.connect_errors = []
        self.created = []
        self.set_calls = []

    def ls(self, **kwargs):
        return list(self.files) if kwargs.get("type") == "file" else []

    def getAttr(self, plug):
        node, _sep, attr = plug.partition(".")
        if attr == "fileTextureName":
            return self.paths.get(node, "")
        if attr == _MARKER:
            return self.markers.get(node)
        return None

    def attributeQuery(self, attr, node=None, exists=True):
        return attr == _MARKER and node in self.markers

    def addAttr(self, node, longName=None, dataType=None):
        self.set_calls.append((node, longName))

    def setAttr(self, plug, *args, **kwargs):
        node, _sep, attr = plug.partition(".")
        value = args[0] if args else None
        if attr == "fileTextureName":
            self.paths[node] = value
        elif attr == _MARKER:
            self.markers[node] = value
        self.set_calls.append((plug, value))

    def listConnections(self, plug, **kwargs):
        node, _sep, attr = plug.partition(".")
        return list(self.uv_upstream.get((node, attr), []))

    def nodeType(self, node):
        return self.node_types.get(node, "unknown")

    def isConnected(self, src, dst):
        return (src, dst) in self.connected

    def connectAttr(self, src, dst, force=True):
        if self.connect_errors:
            error = self.connect_errors.pop(0)
            if error is not None:
                raise error
        self.connect_calls.append((src, dst))
        self.connected.add((src, dst))

    def shadingNode(self, node_type, **kwargs):
        name = kwargs.get("name") or ("%s1" % node_type)
        self.created.append((node_type, name))
        return name


def _make(monkeypatch):
    fake = FakeBumpCmds()
    monkeypatch.setattr(bump_module, "cmds", fake)
    converter = BumpConverter(None, None, logger=Logger())
    return converter, fake


def _complete_chain(fake, file_node, p2d="p2d1"):
    fake.node_types[p2d] = "place2dTexture"
    for src_attr, dst_attr in P2D_CONNECTIONS:
        fake.uv_upstream[(file_node, dst_attr)] = ["%s.%s" % (p2d, src_attr)]
        fake.connected.add(("%s.%s" % (p2d, src_attr), "%s.%s" % (file_node, dst_attr)))


def _add_file(fake, node, path, marker=None):
    fake.files.append(node)
    fake.paths[node] = path
    if marker is not None:
        fake.markers[node] = marker


def test_tagged_file_with_complete_chain_is_reused(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/n.png", marker="bn1")
    _complete_chain(fake, "tex_bn1")

    assert converter._find_existing_embedded_file("bn1", "C:/n.png") == "tex_bn1"


def test_tagged_file_with_broken_chain_is_repaired(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/n.png", marker="bn1")
    fake.node_types["p2d1"] = "place2dTexture"
    monkeypatch.setattr(converter, "_find_place2d", lambda node: "p2d1")

    assert converter._find_existing_embedded_file("bn1", "C:/n.png") == "tex_bn1"
    assert fake.connect_calls  # UV connections were repaired


def test_tagged_file_owned_by_another_source_is_not_reused(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/n.png", marker="otherBn")
    _complete_chain(fake, "tex_bn1")

    assert converter._find_existing_embedded_file("bn1", "C:/n.png") is None


def test_untagged_complete_file_is_reused_for_legacy_scenes(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/n.png")
    _complete_chain(fake, "tex_bn1")

    assert converter._find_existing_embedded_file("bn1", "C:/n.png") == "tex_bn1"


def test_untagged_incomplete_file_is_not_reused(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/n.png")

    assert converter._find_existing_embedded_file("bn1", "C:/n.png") is None


def test_file_with_other_path_is_not_reused(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/other.png", marker="bn1")
    _complete_chain(fake, "tex_bn1")

    assert converter._find_existing_embedded_file("bn1", "C:/n.png") is None


def test_file_index_is_cached_until_reset(monkeypatch):
    converter, fake = _make(monkeypatch)
    _add_file(fake, "tex_bn1", "C:/n.png", marker="bn1")
    _complete_chain(fake, "tex_bn1")

    calls = []
    original_ls = fake.ls

    def counting_ls(**kwargs):
        calls.append(kwargs)
        return original_ls(**kwargs)

    fake.ls = counting_ls
    converter._find_existing_embedded_file("bn1", "C:/n.png")
    converter._find_existing_embedded_file("bn1", "C:/n.png")
    assert len(calls) == 1

    converter.reset_index()
    converter._find_existing_embedded_file("bn1", "C:/n.png")
    assert len(calls) == 2


def test_missing_place2d_is_a_critical_failure(monkeypatch):
    converter, fake = _make(monkeypatch)
    monkeypatch.setattr(converter, "_find_place2d", lambda node: None)
    monkeypatch.setattr(converter, "_create_place2d", lambda node: None)

    node, ok = converter._build_file_from_path(
        "bn1", "C:/n.png", types.SimpleNamespace())

    assert node is None
    assert ok is False
    assert fake.created == []  # no half-wired file node left behind


def test_new_file_node_is_tagged_with_its_source(monkeypatch):
    converter, fake = _make(monkeypatch)
    fake.node_types["p2d1"] = "place2dTexture"
    monkeypatch.setattr(converter, "_find_place2d", lambda node: "p2d1")

    node, ok = converter._build_file_from_path(
        "bn1", "C:/n.png", types.SimpleNamespace())

    assert ok
    assert node == "tex_bn1"
    assert fake.paths[node] == "C:/n.png"
    assert fake.markers[node] == "bn1"


def test_p2d_connection_failure_is_a_critical_failure(monkeypatch):
    converter, fake = _make(monkeypatch)
    fake.node_types["p2d1"] = "place2dTexture"
    monkeypatch.setattr(converter, "_find_place2d", lambda node: "p2d1")
    fake.connect_errors = [None] * (len(P2D_CONNECTIONS) - 1) + [RuntimeError("locked")]

    node, ok = converter._build_file_from_path(
        "bn1", "C:/n.png", types.SimpleNamespace())

    assert node is None
    assert ok is False

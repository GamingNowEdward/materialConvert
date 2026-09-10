"""Shared colorspace matching core.

Single source of truth for automatic colorspace matching. Migrated from the
former NodeToolsTab implementation: name keyword matching, downstream channel
BFS tracing and role -> alias -> actual Maya colorspace resolution.

All rules still come from the existing configuration system
(``colorSpace.json`` / ``texture_channels.json`` / material configs via
``ConfigLoader``); no second rule set is defined here.
"""

import os
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

import maya.cmds as cmds

from core.config_loader import ConfigLoader, normalize_keyword
from core.logger import get_logger

_SOURCE = "ColorSpaceCore"


class DriverStatus(Enum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


class MatchState(Enum):
    MATCHED = "MATCHED"
    CONFLICT = "CONFLICT"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"
    INVALID = "INVALID"


@dataclass
class NameDriverResult:
    status: DriverStatus = DriverStatus.NO_MATCH
    roles: list = field(default_factory=list)
    reason: str = ""


@dataclass
class ChannelDriverResult:
    status: DriverStatus = DriverStatus.NO_MATCH
    roles: list = field(default_factory=list)
    reason: str = ""


@dataclass
class MatchResult:
    file_node: str
    file_path: str
    actual_colorspace: str
    name_driver_result: NameDriverResult
    channel_driver_result: ChannelDriverResult
    prematch_colorspace: str
    state: MatchState
    diagnostic: str


def _result_from_roles(roles, no_match_reason, ambiguous_reason):
    """Reduce a collected role list to a driver result.

    0 roles -> NO_MATCH, 1 role -> MATCH, more -> AMBIGUOUS.
    """
    roles = list(roles)
    if not roles:
        return DriverStatus.NO_MATCH, roles, no_match_reason
    if len(roles) == 1:
        return DriverStatus.MATCH, roles, ""
    return DriverStatus.AMBIGUOUS, roles, ambiguous_reason


class NameDriver:

    def __init__(self, config_loader=None, logger=None):
        self.config = config_loader or ConfigLoader()
        self.log = logger or get_logger()
        self._filename_role_keywords = self.config.get_filename_role_keywords()

    def match(self, file_path):
        """Match a file path to one or more colorspace roles from its basename."""
        if not file_path:
            return NameDriverResult(DriverStatus.NO_MATCH, [], "file path is empty")
        filename = os.path.basename(file_path).lower().replace("_", "").replace("-", "")
        if not filename:
            return NameDriverResult(DriverStatus.NO_MATCH, [], "no filename")

        roles = []
        for role, keywords in self._filename_role_keywords.items():
            for kw in keywords:
                if kw in filename:
                    roles.append(role)
                    break

        status, roles, reason = _result_from_roles(
            roles,
            "no filename keyword matched",
            f"multiple roles matched: {', '.join(roles)}",
        )
        return NameDriverResult(status, roles, reason)


class ChannelDriver:

    _TRACE_NODE_BUDGET = 1000

    _TRACE_SKIP_NODES = {
        # Maya default bookkeeping containers.
        "defaultTextureList1", "defaultRenderUtilityList1",
        "defaultShaderList1", "defaultColorMgtGlobals",
        # Texture/UV source nodes. They are not material targets and should
        # never be traversed as downstream shading nodes.
        "place2dTexture", "file",
    }

    _DEFAULT_MAX_DEPTH = 4

    def __init__(self, config_loader=None, logger=None):
        self.config = config_loader or ConfigLoader()
        self.log = logger or get_logger()
        self.expanded_keywords = self.config.get_expanded_attribute_keywords()
        self._shader_types = None
        self._material_node_cache = {}

    def reset(self):
        """Clear per-refresh caches (material node lookups, shader types)."""
        self._shader_types = None
        self._material_node_cache = {}

    def _get_shader_types(self):
        if self._shader_types is None:
            try:
                self._shader_types = set(cmds.listNodeTypes("shader") or [])
            except Exception as exc:
                self.log.warn(f"Failed to list shader node types: {exc}", source=_SOURCE)
                self._shader_types = set()
        return self._shader_types

    def _is_material_node(self, node):
        """Return True when *node* is a shader node type.

        Uses ``listNodeTypes("shader")`` instead of probing ``node.outColor``.
        Probing ``.outColor`` is both expensive and invalid for utility nodes
        such as place2dTexture, which produced warning floods and slowed large
        Auto Match operations to a crawl.
        """
        cached = self._material_node_cache.get(node)
        if cached is not None:
            return cached

        try:
            result = cmds.nodeType(node) in self._get_shader_types()
        except Exception as exc:
            self.log.warn(f"Failed to identify node type for {node}: {exc}", source=_SOURCE)
            result = False

        self._material_node_cache[node] = result
        return result

    def trace_channel_targets(self, file_node, max_depth=_DEFAULT_MAX_DEPTH):
        """BFS trace all output endpoints of a file node, returning the list of
        attribute names on hit materials.
        """
        targets = []
        material_targets = set()
        visited = {file_node}
        queue = deque([(file_node, 0)])
        checked = 0
        budget_exceeded = False

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            try:
                destinations = cmds.listConnections(
                    node, plugs=True, source=False, destination=True
                ) or []
            except Exception as exc:
                self.log.warn(f"Failed to trace downstream from {node}: {exc}", source=_SOURCE)
                continue

            for dest in dict.fromkeys(destinations):
                if "." not in dest:
                    continue
                dnode, attr_path = dest.split(".", 1)
                if dnode in self._TRACE_SKIP_NODES:
                    continue

                if self._is_material_node(dnode):
                    target_attr = attr_path.rsplit(".", 1)[-1]
                    key = (dnode, target_attr)
                    if key not in material_targets:
                        material_targets.add(key)
                        targets.append(target_attr)
                    continue

                if dnode in visited:
                    continue

                checked += 1
                if checked > self._TRACE_NODE_BUDGET:
                    budget_exceeded = True
                    break

                visited.add(dnode)
                queue.append((dnode, depth + 1))

            if budget_exceeded:
                self.log.warn(
                    f"Channel trace budget exceeded for {file_node} "
                    f"({self._TRACE_NODE_BUDGET} nodes); using partial targets",
                    source=_SOURCE,
                )
                break

        return targets

    def match(self, file_node):
        """Match a file node to colorspace roles from its downstream material
        channel attributes. Multiple conflicting channel roles -> AMBIGUOUS.
        """
        roles = []
        for attr_name in self.trace_channel_targets(file_node):
            n_attr = normalize_keyword(attr_name)
            for role, keywords in self.expanded_keywords.items():
                if n_attr in keywords:
                    if role not in roles:
                        roles.append(role)

        status, roles, reason = _result_from_roles(
            roles,
            "no material channel matched",
            f"conflicting channels resolved to multiple roles: {', '.join(roles)}",
        )
        return ChannelDriverResult(status, roles, reason)


class ColorSpaceResolver:

    def __init__(self, config_loader=None, logger=None):
        self.config = config_loader or ConfigLoader()
        self.log = logger or get_logger()
        self.cs_config = self.config.get_color_space_config()
        self._available = None

    def reset(self):
        self._available = None

    def available_spaces(self):
        if self._available is None:
            try:
                result = cmds.colorManagementPrefs(q=True, inputSpaceNames=True) or []
            except Exception as exc:
                self.log.warn(f"Failed to query available color spaces: {exc}", source=_SOURCE)
                result = []
            self._available = set(result)
        return set(self._available)

    def resolve(self, role):
        """Resolve an internal role to an actual Maya colorspace name.

        Returns the first alias present in the current Maya color management
        working spaces, or ``None`` when the role cannot be resolved. Never
        silently falls back to another colorspace.
        """
        cs_data = self.cs_config.get("colorSpaces", {}).get(role, {})
        available = self.available_spaces()
        for cs_name in cs_data.get("aliases", []):
            if cs_name in available:
                return cs_name
        return None


class ColorSpaceMatcher:

    def __init__(self, resolver=None, name_driver=None, channel_driver=None, logger=None,
                 config_loader=None):
        self.log = logger or get_logger()
        self.resolver = resolver or ColorSpaceResolver(
            config_loader=config_loader, logger=self.log)
        self.name_driver = name_driver or NameDriver(
            config_loader=config_loader, logger=self.log)
        self.channel_driver = channel_driver or ChannelDriver(
            config_loader=config_loader, logger=self.log)

    def reset(self):
        """Clear per-refresh caches without touching the scene."""
        self.resolver.reset()
        self.channel_driver.reset()

    def available_spaces(self):
        return self.resolver.available_spaces()

    def scan(self):
        file_nodes = cmds.ls(type="file") or []
        self.reset()
        return [self.match(node) for node in file_nodes]

    def apply_matched(self, results):
        """Apply prematch colorspaces for MATCHED ``MatchResult`` entries only.

        Accepts the ``MatchResult`` objects returned by :meth:`scan`; every
        non-MATCHED result is counted as skipped and never applied.
        """
        assignments = []
        skip_count = 0
        for result in results:
            if result.state == MatchState.MATCHED:
                assignments.append((result.file_node, result.prematch_colorspace))
            else:
                skip_count += 1
        return self._set_colorspaces(assignments, skip_count=skip_count)

    def set_colorspace(self, nodes, colorspace):
        return self._set_colorspaces([(node, colorspace) for node in nodes])

    def ignore_color_space_file_rules(self):
        file_nodes = cmds.ls(type="file") or []
        applied = []
        failed = []
        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.log.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        try:
            for node in file_nodes:
                try:
                    cmds.setAttr(f"{node}.ignoreColorSpaceFileRules", 1)
                    applied.append(node)
                except Exception as exc:
                    failed.append((node, exc))
                    self.log.warn(
                        f"Failed to set ignoreColorSpaceFileRules on {node}: {exc}",
                        source=_SOURCE,
                    )
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.log.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        return {"nodes": file_nodes, "applied": applied, "failed": failed}

    def _set_colorspaces(self, assignments, skip_count=0):
        applied = []
        failed = []
        try:
            cmds.undoInfo(openChunk=True)
        except Exception as exc:
            self.log.warn(f"Failed to open undo chunk: {exc}", source=_SOURCE)

        try:
            for node, colorspace in assignments:
                if not colorspace:
                    skip_count += 1
                    continue
                try:
                    cmds.setAttr(f"{node}.colorSpace", colorspace, type="string")
                    applied.append((node, colorspace))
                except Exception as exc:
                    failed.append((node, exc))
                    self.log.warn(
                        f"Failed to set color space on {node}: {exc}",
                        source=_SOURCE,
                    )
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                self.log.warn(f"Failed to close undo chunk: {exc}", source=_SOURCE)

        return {"applied": applied, "failed": failed, "skipped": skip_count}

    def match(self, file_node):
        """Compute the match result for a single Maya file node. Read-only."""
        errors = []
        path = self._read_file_path(file_node, errors)
        actual = self._read_actual_colorspace(file_node, errors)

        name_res = self.name_driver.match(path)
        channel_res = self.channel_driver.match(file_node)

        state, prematch, diagnostic = self._combine(name_res, channel_res)
        if errors:
            diagnostic = "; ".join(errors) + (f" | {diagnostic}" if diagnostic else "")

        return MatchResult(
            file_node=file_node,
            file_path=path,
            actual_colorspace=actual,
            name_driver_result=name_res,
            channel_driver_result=channel_res,
            prematch_colorspace=prematch,
            state=state,
            diagnostic=diagnostic,
        )

    def _read_file_path(self, file_node, errors):
        try:
            return cmds.getAttr(f"{file_node}.fileTextureName") or ""
        except Exception as exc:
            self.log.warn(f"Failed to read fileTextureName on {file_node}: {exc}", source=_SOURCE)
            errors.append(f"error reading file path: {exc}")
            return ""

    def _read_actual_colorspace(self, file_node, errors):
        try:
            return cmds.getAttr(f"{file_node}.colorSpace") or ""
        except Exception as exc:
            self.log.warn(f"Failed to read colorSpace on {file_node}: {exc}", source=_SOURCE)
            errors.append(f"error reading colorSpace: {exc}")
            return ""

    def _combine(self, name_res, channel_res):
        """Reduce driver results to a final match state and prematch colorspace."""
        if (name_res.status == DriverStatus.AMBIGUOUS
                or channel_res.status == DriverStatus.AMBIGUOUS):
            diagnostic = (
                f"name: {self._driver_line(name_res)}; "
                f"channel: {self._driver_line(channel_res)}"
            )
            return MatchState.AMBIGUOUS, "", diagnostic

        if name_res.status == DriverStatus.MATCH and channel_res.status == DriverStatus.MATCH:
            name_role = name_res.roles[0]
            channel_role = channel_res.roles[0]
            if name_role != channel_role:
                return (
                    MatchState.CONFLICT,
                    "",
                    f"filename -> {name_role}, channel -> {channel_role}",
                )
            role = name_role
        elif name_res.status == DriverStatus.MATCH:
            role = name_res.roles[0]
        elif channel_res.status == DriverStatus.MATCH:
            role = channel_res.roles[0]
        else:
            return MatchState.UNMATCHED, "", "no match from filename or channel"

        prematch = self.resolver.resolve(role)
        if prematch is None:
            return (
                MatchState.INVALID,
                "",
                f"role '{role}' could not be resolved to an available Maya colorspace",
            )
        return MatchState.MATCHED, prematch, f"matched role '{role}'"

    @staticmethod
    def _driver_line(result):
        if result.status == DriverStatus.MATCH:
            return result.roles[0]
        if result.status == DriverStatus.NO_MATCH:
            return "no match"
        return f"ambiguous ({', '.join(result.roles)})"
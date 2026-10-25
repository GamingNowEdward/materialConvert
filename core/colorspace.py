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
from core.filename_match import (ChannelMatcher, normalize_stem, shared_keywords,
                                 short_suffix_letters)
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
class TraceResult:
    """Outcome of a downstream channel trace.

    ``complete`` False means the search hit its depth or node budget and the
    target set may be partial: "no conflicting channel found" must never be
    presented as "there is no conflicting channel".
    """

    targets: list = field(default_factory=list)
    complete: bool = True
    truncated: bool = False
    depth_limited: bool = False
    errors: list = field(default_factory=list)

    def __iter__(self):
        return iter(self.targets)

    def __len__(self):
        return len(self.targets)

    def __contains__(self, item):
        return item in self.targets

    def __eq__(self, other):
        # Keep list-style comparisons readable in tests and callers.
        if isinstance(other, (list, tuple)):
            return self.targets == list(other)
        return NotImplemented

    def __bool__(self):
        return bool(self.targets)


@dataclass
class NameDriverResult:
    status: DriverStatus = DriverStatus.NO_MATCH
    roles: list = field(default_factory=list)
    reason: str = ""
    evidence_complete: bool = True


@dataclass
class ChannelDriverResult:
    status: DriverStatus = DriverStatus.NO_MATCH
    roles: list = field(default_factory=list)
    reason: str = ""
    evidence_complete: bool = True
    truncated: bool = False
    depth_limited: bool = False
    errors: list = field(default_factory=list)


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
    evidence_complete: bool = True


def _role_for_channel_type(channel_type):
    """Colorspace role of a texture channel, from ``texture_channels.json``.

    Color channels carry colour data (srgb); every data channel (float / normal /
    bump / displacement) is raw.
    """
    return "srgb" if channel_type == "color" else "raw"


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
        # Filename matching is shared with the Batch Builder scanner, so short
        # aliases (col/sss/nrm/...) count too — only as complete tokens.
        self._matcher = ChannelMatcher(
            self.config.get_texture_channels(),
            short_suffixes=self.config.get_short_suffixes(),
            logger=self.log,
        )
        #: Every alias, for callers that need to detect the ones a whole texture
        #: set shares (see ``core.filename_match.shared_keywords``).
        self.aliases = self._matcher.aliases
        #: Single-letter markers (``d`` -> ``BaseColor``), gated per directory
        #: by ``ColorSpaceMatcher.scan`` (see ``short_suffix_letters``).
        self.short_suffixes = self._matcher.short_suffixes

    def match(self, file_path, ignore_aliases=(), enable_short_suffixes=False):
        """Match a file path to one or more colorspace roles from its basename.

        The matched texture channels are mapped to roles by their configured
        ``type`` (color -> srgb, data -> raw) and deduplicated, so two channels of
        the same role are one conclusion while different roles stay ambiguous.

        ``ignore_aliases`` are skipped: an alias shared by every file of a set
        (e.g. a ``_METALNESS`` suffix) is a property of the set, not evidence
        about this file.

        ``enable_short_suffixes`` allows a whitelisted single-letter last token;
        the caller turns it on per directory (see ``short_suffix_letters``).
        """
        if not file_path:
            return NameDriverResult(DriverStatus.NO_MATCH, [], "file path is empty",
                                    evidence_complete=False)
        filename = os.path.basename(file_path)
        if not filename:
            return NameDriverResult(DriverStatus.NO_MATCH, [], "no filename",
                                    evidence_complete=False)

        # Match the stem: a short alias (col/nrm/sss) at the very end would
        # otherwise be glued to the extension ("col.jpg") and never match.
        normalized = normalize_stem(os.path.splitext(filename)[0])
        roles = []
        for match in self._matcher.matches_normalized(
                normalized, ignore_aliases,
                enable_short_suffixes=enable_short_suffixes):
            role = _role_for_channel_type(match.channel_type)
            if role not in roles:
                roles.append(role)

        status, roles, reason = _result_from_roles(
            roles,
            "no filename keyword matched",
            f"multiple roles matched: {', '.join(roles)}",
        )
        return NameDriverResult(status, roles, reason)


class ChannelDriver:

    _TRACE_NODE_BUDGET = 1000

    _TRACE_SKIP_NODES = {
        # Maya default bookkeeping containers (matched by node *name*).
        "defaultTextureList1", "defaultRenderUtilityList1",
        "defaultShaderList1", "defaultColorMgtGlobals",
    }

    #: Node *types* that are not material targets and must never be traversed as
    #: downstream shading nodes.  Matching them by node name was a dead check
    #: (a node literally called "file" is rare).
    _TRACE_SKIP_TYPES = {"file", "place2dTexture"}

    _DEFAULT_MAX_DEPTH = 4

    def __init__(self, config_loader=None, logger=None):
        self.config = config_loader or ConfigLoader()
        self.log = logger or get_logger()
        self.expanded_keywords = self.config.get_expanded_attribute_keywords()
        self._shader_types = None
        self._material_node_cache = {}

    def _is_skip_node(self, dnode):
        """Whether *dnode* is a bookkeeping container or a texture source node."""
        if dnode in self._TRACE_SKIP_NODES:
            return True
        try:
            return cmds.nodeType(dnode) in self._TRACE_SKIP_TYPES
        except Exception as exc:
            self.log.debug(f"Failed to identify node type for {dnode}: {exc}", source=_SOURCE)
            return False

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
        """BFS trace all output endpoints of a file node.

        Returns a :class:`TraceResult` whose ``complete`` flag records whether the
        search was exhaustive; truncated evidence must not be treated as proof
        that no conflicting channel exists.
        """
        trace = TraceResult()
        targets = []
        material_targets = set()
        visited = {file_node}
        queue = deque([(file_node, 0)])
        checked = 0
        budget_exceeded = False

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                # Only mark the trace incomplete when there really is more to
                # explore beyond the depth limit.
                try:
                    probe = cmds.listConnections(
                        node, plugs=True, source=False, destination=True) or []
                except Exception as exc:  # noqa: silent-fallback recorded in trace.errors
                    trace.errors.append(f"failed to probe downstream of {node}: {exc}")
                    trace.complete = False
                    continue
                if any(not self._is_skip_node(dest.split(".", 1)[0])
                       for dest in probe if "." in dest):
                    trace.depth_limited = True
                    trace.complete = False
                continue
            try:
                destinations = cmds.listConnections(
                    node, plugs=True, source=False, destination=True
                ) or []
            except Exception as exc:
                trace.errors.append(f"failed to trace downstream from {node}: {exc}")
                trace.complete = False
                self.log.warn(f"Failed to trace downstream from {node}: {exc}", source=_SOURCE)
                continue

            for dest in dict.fromkeys(destinations):
                if "." not in dest:
                    continue
                dnode, attr_path = dest.split(".", 1)
                if self._is_skip_node(dnode):
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
                trace.truncated = True
                trace.complete = False
                self.log.warn(
                    f"Channel trace budget exceeded for {file_node} "
                    f"({self._TRACE_NODE_BUDGET} nodes); using partial targets",
                    source=_SOURCE,
                )
                break

        trace.targets = targets
        return trace

    def match(self, file_node):
        """Match a file node to colorspace roles from its downstream material
        channel attributes. Multiple conflicting channel roles -> AMBIGUOUS.
        """
        trace = self.trace_channel_targets(file_node)
        roles = []
        for attr_name in trace.targets:
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
        return ChannelDriverResult(
            status=status,
            roles=roles,
            reason=reason,
            evidence_complete=trace.complete,
            truncated=trace.truncated,
            depth_limited=trace.depth_limited,
            errors=list(trace.errors),
        )


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

        paths = {node: self._read_path_quiet(node) for node in file_nodes}
        shared = self._shared_name_keywords(paths)
        for directory in sorted(shared):
            self.log.info(
                f"Ignoring common filename keyword(s) in {directory}: "
                f"{', '.join(sorted(shared[directory]))}",
                source=_SOURCE,
            )
        short = self._short_suffix_directories(paths)

        results = [
            self.match(node,
                       ignore_aliases=shared.get(os.path.dirname(paths[node]), ()),
                       enable_short_suffixes=short.get(os.path.dirname(paths[node]), False))
            for node in file_nodes
        ]
        if shared and not any(
                result.name_driver_result.status == DriverStatus.MATCH for result in results):
            # Nothing was classified from the file name once the set-wide keywords
            # were ignored (e.g. a directory holding only metallic maps), so they
            # really were the evidence: scan again without the filter.
            self.log.info(
                "No filename role resolved with the common keywords ignored; "
                "scanning again without the common-keyword filter",
                source=_SOURCE,
            )
            results = [
                self.match(node, enable_short_suffixes=short.get(
                    os.path.dirname(paths[node]), False))
                for node in file_nodes
            ]
        return results

    def _short_suffix_directories(self, paths):
        """Per-directory gate for single-letter channel markers.

        A directory qualifies when at least two distinct whitelisted letters
        appear as file-name last tokens (see ``short_suffix_letters``).
        """
        stems_by_directory = {}
        for path in paths.values():
            if not path:
                continue
            directory = os.path.dirname(path)
            stems_by_directory.setdefault(directory, []).append(
                os.path.splitext(os.path.basename(path))[0])
        return {
            directory: len(short_suffix_letters(stems, self.name_driver.short_suffixes)) >= 2
            for directory, stems in stems_by_directory.items()
        }

    def _shared_name_keywords(self, paths):
        """Per-directory filename keywords shared by most files of that set."""
        stems_by_directory = {}
        for path in paths.values():
            if not path:
                continue
            directory = os.path.dirname(path)
            stems_by_directory.setdefault(directory, []).append(
                os.path.splitext(os.path.basename(path))[0])

        shared = {}
        for directory, stems in stems_by_directory.items():
            common = shared_keywords(stems, self.name_driver.aliases)
            if common:
                shared[directory] = common
        return shared

    def apply_matched(self, results, revalidate=False):
        """Apply prematch colorspaces for MATCHED ``MatchResult`` entries only.

        Accepts the ``MatchResult`` objects returned by :meth:`scan`; every
        non-MATCHED result is counted as skipped and never applied.  With
        ``revalidate=True`` each candidate is re-evaluated against the live scene
        right before applying, so a stale scan (re-path, OCIO change) can never
        silently write an outdated colorspace.
        """
        assignments = []
        skip_count = 0
        stale = []
        for result in results:
            if result.state != MatchState.MATCHED:
                skip_count += 1
                continue
            if revalidate:
                fresh = self.match(result.file_node)
                if (fresh.state != MatchState.MATCHED
                        or fresh.prematch_colorspace != result.prematch_colorspace):
                    stale.append(result.file_node)
                    skip_count += 1
                    self.log.warn(
                        f"Colorspace recommendation for {result.file_node} is stale "
                        f"({result.prematch_colorspace!r} -> "
                        f"{fresh.prematch_colorspace!r}); not applied",
                        source=_SOURCE,
                    )
                    continue
            assignments.append((result.file_node, result.prematch_colorspace))
        outcome = self._set_colorspaces(assignments, skip_count=skip_count)
        outcome["stale"] = stale
        return outcome

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

    def match(self, file_node, ignore_aliases=(), enable_short_suffixes=False):
        """Compute the match result for a single Maya file node. Read-only."""
        errors = []
        path = self._read_file_path(file_node, errors)
        actual = self._read_actual_colorspace(file_node, errors)

        name_res = self.name_driver.match(path, ignore_aliases, enable_short_suffixes)
        channel_res = self.channel_driver.match(file_node)

        state, prematch, diagnostic = self._combine(name_res, channel_res)
        evidence_complete = name_res.evidence_complete and channel_res.evidence_complete
        if errors:
            diagnostic = "; ".join(errors) + (f" | {diagnostic}" if diagnostic else "")
            evidence_complete = False

        return MatchResult(
            file_node=file_node,
            file_path=path,
            actual_colorspace=actual,
            name_driver_result=name_res,
            channel_driver_result=channel_res,
            prematch_colorspace=prematch,
            state=state,
            diagnostic=diagnostic,
            evidence_complete=evidence_complete,
        )

    def _read_file_path(self, file_node, errors):
        try:
            return cmds.getAttr(f"{file_node}.fileTextureName") or ""
        except Exception as exc:
            self.log.warn(f"Failed to read fileTextureName on {file_node}: {exc}", source=_SOURCE)
            errors.append(f"error reading file path: {exc}")
            return ""

    def _read_path_quiet(self, file_node):
        """Read a file path for the pre-pass, without duplicating error reports."""
        try:
            return cmds.getAttr(f"{file_node}.fileTextureName") or ""
        except Exception as exc:
            self.log.debug(f"Failed to read fileTextureName on {file_node}: {exc}", source=_SOURCE)
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
            if not channel_res.evidence_complete:
                # A partial trace can only prove what it saw, not that nothing
                # else exists: do not auto-apply on that basis.
                detail = self._incomplete_reason(channel_res)
                return (
                    MatchState.AMBIGUOUS,
                    "",
                    f"channel match '{channel_res.roles[0]}' rests on incomplete "
                    f"evidence ({detail}); manual confirmation required",
                )
            role = channel_res.roles[0]
        else:
            diagnostic = "no match from filename or channel"
            if not channel_res.evidence_complete:
                diagnostic += (
                    f" (channel trace incomplete: {self._incomplete_reason(channel_res)}; "
                    f"result is not exhaustive)"
                )
            return MatchState.UNMATCHED, "", diagnostic

        prematch = self.resolver.resolve(role)
        if prematch is None:
            return (
                MatchState.INVALID,
                "",
                f"role '{role}' could not be resolved to an available Maya colorspace",
            )
        return MatchState.MATCHED, prematch, f"matched role '{role}'"

    @staticmethod
    def _incomplete_reason(result):
        parts = []
        if getattr(result, "truncated", False):
            parts.append("node budget exceeded")
        if getattr(result, "depth_limited", False):
            parts.append("depth limit reached")
        errors = getattr(result, "errors", None) or []
        if errors:
            parts.append(f"{len(errors)} read error(s)")
        return ", ".join(parts) or "incomplete trace"

    @staticmethod
    def _driver_line(result):
        if result.status == DriverStatus.MATCH:
            return result.roles[0]
        if result.status == DriverStatus.NO_MATCH:
            return "no match"
        return f"ambiguous ({', '.join(result.roles)})"
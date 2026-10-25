"""Filename -> texture-channel matching, shared by the Batch Builder scanner and
the Colorspace name driver.

Pure logic only: nothing here scans a directory or touches Maya.  The channel
definitions come from ``config/texture_channels.json`` and are handed in by the
caller (``TextureScanner`` loads them itself, ``ColorSpaceMatcher`` gets them from
``ConfigLoader``), so both consumers match names by exactly the same rules.
"""

import math
import re
from dataclasses import dataclass

from core.logger import get_logger

#: An alias token shared by at least this fraction of a texture set is treated as
#: a set-wide suffix (part of the material name), not as the marker of that
#: file's channel.  A set whose files all end in e.g. ``_METALNESS`` would
#: otherwise be detected as metallic maps across the board.
_COMMON_TOKEN_RATIO = 0.6
#: "Shared by most files" only means something with enough files, and the token
#: must appear in at least this many of them.
_COMMON_TOKEN_MIN_FILES = 3

#: Bit depths a channel token may carry (standalone ``16`` or glued ``nrm16``).
_BIT_DEPTHS = (8, 16, 32)
#: ``16``-style and ``2k``-style numbers, standalone or glued to a token.
_SUFFIX_RE = re.compile(r"(\d+)(k?)")
#: A numeric suffix glued to an alias: ``nrm16`` / ``rough4k``.
_GLUED_SUFFIX_RE = re.compile(r"\d+k?")


def normalize_stem(name):
    """Lowercase a filename stem, turning dashes/spaces into underscores.

    The token boundaries produced here are the ones every consumer matches
    against, so short aliases never match inside unrelated words.
    """
    return re.sub(r"[- ]", "_", name.lower())


def find_alias(normalized, alias):
    """Return ``(start, end)`` of *alias* in *normalized*, or None.

    Priority:
    1. Exact token match (safe for short aliases).
    2. Token match with a numeric suffix glued on (``nrm16`` -> ``nrm``,
       ``rough4k`` -> ``rough``): texture libraries commonly append a bit depth
       or resolution to the channel token.
    3. Substring match ignoring underscores, only for longer aliases, and only
       when the alias is bounded by non-alphanumeric characters.
    """
    offset = 0
    for token in normalized.split("_"):
        if token == alias:
            return offset, offset + len(alias)
        suffix = token[len(alias):]
        if token.startswith(alias) and _GLUED_SUFFIX_RE.fullmatch(suffix):
            # The whole token is the match: the numeric suffix is part of it.
            return offset, offset + len(token)
        offset += len(token) + 1

    if len(alias) < 4:
        return None

    n = len(normalized)
    i = 0
    while i < n:
        if normalized[i] == "_":
            i += 1
            continue

        start = i
        j = i
        k = 0
        while j < n and k < len(alias):
            if normalized[j] == "_":
                j += 1
                continue
            if normalized[j] != alias[k]:
                break
            k += 1
            j += 1

        if k == len(alias):
            before = normalized[start - 1] if start > 0 else ""
            after = normalized[j] if j < n else ""

            if (not before.isalnum()) and (not after.isalnum()):
                return start, j

        i += 1

    return None


def quality_key(stem):
    """``(bit_depth, resolution)`` parsed from a file stem; higher wins.

    Used to pick between several files of the same channel, whether the value is
    a standalone token (``_16``, ``_2k``) or glued to the channel token
    (``nrm16``, ``nrm4k``).  Only *relative* values matter: candidates come from
    the same set, so numbers every file shares (an asset name's ``004``, a common
    ``2k``) cancel out.
    """
    depth = 0
    resolution = 0
    for token in normalize_stem(stem).split("_"):
        for match in _SUFFIX_RE.finditer(token):
            value = int(match.group(1))
            if match.group(2):
                resolution = max(resolution, value)
            elif value in _BIT_DEPTHS:
                depth = max(depth, value)
    return depth, resolution


def shared_keywords(stems, keywords, ratio=_COMMON_TOKEN_RATIO,
                    min_files=_COMMON_TOKEN_MIN_FILES):
    """Keywords shared by most of *stems*: set-wide suffixes, not file evidence.

    A texture set whose files all end in e.g. ``_METALNESS`` says nothing about
    an individual file, so such a keyword must not be used to classify it.  A
    keyword counts once per stem and only the given *keywords* are considered, so
    an asset name is never treated as common.  Returns an empty set for
    directories too small for "shared by most files" to mean anything.
    """
    total = len(stems)
    if total < min_files:
        return set()

    counts = {}
    for stem in stems:
        for token in set(normalize_stem(stem).split("_")):
            for keyword in keywords:
                if token == keyword or (
                        token.startswith(keyword)
                        and _GLUED_SUFFIX_RE.fullmatch(token[len(keyword):])):
                    counts[keyword] = counts.get(keyword, 0) + 1

    threshold = max(min_files, math.ceil(ratio * total))
    return {keyword for keyword, count in counts.items() if count >= threshold}


@dataclass(frozen=True)
class ChannelMatch:
    """One texture channel matched by a file name."""

    channel: str
    common_attr: str
    channel_type: str
    alias: str
    span: tuple


class ChannelMatcher:
    """Which texture channels a file name matches.

    Knows nothing about the directory or the scene: callers decide what to do
    with the matches (the scanner picks one and derives a material name, the
    Colorspace name driver maps them to colorspace roles).
    """

    def __init__(self, channels, logger=None):
        self.log = logger or get_logger()
        self.channels = channels or {}
        self._candidates = self._compile_candidates()
        #: Distinct aliases, longest first (the tie-break order for matching).
        ordered = []
        for _channel_name, _channel_data, alias in self._candidates:
            if alias not in ordered:
                ordered.append(alias)
        self._aliases_by_length = tuple(ordered)
        #: The same aliases as a set, for membership tests.
        self.aliases = frozenset(ordered)

    def _compile_candidates(self):
        candidates = []
        for channel_name, channel_data in self.channels.items():
            if not isinstance(channel_data, dict):
                self.log.error(f"Texture channel '{channel_name}' is not an object; ignored",
                               source="ChannelMatcher")
                continue
            for alias in channel_data.get("aliases", []):
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                candidates.append((channel_name, channel_data, alias_norm))
        candidates.sort(key=lambda item: len(item[2]), reverse=True)
        return candidates

    def alias_of_token(self, token):
        """Alias matched by one normalized token, or None.

        Exact token equality first, then a numeric suffix glued to the alias
        (``nrm16`` -> ``nrm``).  Only token-bounded matches are considered, so
        short aliases stay safe.
        """
        if token in self.aliases:
            return token
        for name in self._aliases_by_length:
            suffix = token[len(name):]
            if token.startswith(name) and _GLUED_SUFFIX_RE.fullmatch(suffix):
                return name
        return None

    def matches_normalized(self, normalized, ignore_aliases=()):
        """Every channel *normalized* matches, longest alias first.

        ``ignore_aliases`` are skipped: they belong to the whole set (see
        :func:`shared_keywords`) and are not evidence about one file.
        """
        matches = []
        for channel_name, channel_data, alias_norm in self._candidates:
            if alias_norm in ignore_aliases:
                continue
            found = find_alias(normalized, alias_norm)
            if not found:
                continue
            matches.append(ChannelMatch(
                channel=channel_name,
                common_attr=channel_data.get("common_attr", ""),
                channel_type=channel_data.get("type", ""),
                alias=alias_norm,
                span=found,
            ))
        return matches

    def matches(self, stem, ignore_aliases=()):
        """Every channel *stem* matches, longest alias first."""
        return self.matches_normalized(normalize_stem(stem), ignore_aliases)

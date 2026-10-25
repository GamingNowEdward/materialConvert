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
from functools import lru_cache

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
#: A single-letter channel token, optionally with a strength/resolution number:
#: ``d`` / ``b005`` / ``r100``.  Some libraries (Arroway, Finex) mark the channel
#: with one letter at the very end of the name.
_SHORT_TOKEN_RE = re.compile(r"([a-z])(\d+k?)?")


def normalize_stem(name):
    """Lowercase a filename stem, turning separators into underscores.

    Dashes, spaces and parentheses all become ``_``, so ``(g000)`` and
    ``s050-g025`` split into the same tokens every consumer matches against and
    short aliases never match inside unrelated words.
    """
    return re.sub(r"[- ()]", "_", name.lower())


@lru_cache(maxsize=None)
def _underscore_pattern(alias):
    """Regex matching *alias* in a normalized stem with underscores ignored.

    The alias' own underscores are dropped first, so ``base_color`` and
    ``basecolor`` are the same token, and underscores are then allowed between
    the remaining characters (``met_allic`` matches ``metallic``).  Cached: the
    alias table is fixed and this runs once per file per alias.
    """
    cleaned = alias.replace("_", "")
    if not cleaned:
        return None
    return re.compile(r"_*".join(re.escape(char) for char in cleaned))


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
    for match in re.finditer(r"[^_]+", normalized):
        token = match.group()
        start, end = match.span()

        if token == alias:
            return start, end

        suffix = token[len(alias):]
        if token.startswith(alias) and _GLUED_SUFFIX_RE.fullmatch(suffix):
            # The whole token is the match: the numeric suffix is part of it.
            return start, end

    if len(alias) < 4:
        return None

    pattern = _underscore_pattern(alias)
    if pattern is None:
        return None

    for match in pattern.finditer(normalized):
        start, end = match.span()
        before = normalized[start - 1] if start > 0 else ""
        after = normalized[end] if end < len(normalized) else ""

        if (not before.isalnum()) and (not after.isalnum()):
            return start, end

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


def token_matches(token, keyword):
    """Whether a normalized *token* is *keyword* or *keyword* plus a glued number.

    ``nrm`` matches ``nrm`` and ``nrm16``; a bare letter matches ``g`` and
    ``g025``.  Used by :func:`shared_keywords` and by the scanner's manual
    ignore list, so both apply the same "letter + strength" rule.
    """
    if token == keyword:
        return True
    if not keyword:
        return False
    suffix = token[len(keyword):]
    return (token.startswith(keyword)
            and _GLUED_SUFFIX_RE.fullmatch(suffix) is not None)


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
                if token_matches(token, keyword):
                    counts[keyword] = counts.get(keyword, 0) + 1

    threshold = max(min_files, math.ceil(ratio * total))
    return {keyword for keyword, count in counts.items() if count >= threshold}


def short_suffix_letters(stems, table):
    """Whitelisted single-letter channels used as the last token of *stems*.

    Returns the set of distinct letters (keys of *table*) that appear as the
    final token of at least one stem, in bare (``d``) or numbered form
    (``b005``, ``r100``).  Callers use the size of this set as a directory-level
    gate: a lone letter is too weak to be evidence, but several distinct letters
    in one set mean the library is using single-letter channel markers.
    """
    if not table:
        return set()
    letters = set()
    for stem in stems:
        tokens = normalize_stem(stem).split("_")
        if not tokens:
            continue
        match = _SHORT_TOKEN_RE.fullmatch(tokens[-1])
        if match and match.group(1) in table:
            letters.add(match.group(1))
    return letters


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

    def __init__(self, channels, short_suffixes=None, logger=None):
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
        #: Single-letter channel markers (``d`` -> ``BaseColor``); only honoured
        #: when the caller has confirmed them for the directory being scanned.
        self.short_suffixes = self._compile_short_suffixes(short_suffixes)

    def _compile_short_suffixes(self, short_suffixes):
        table = {}
        for letter, channel_name in (short_suffixes or {}).items():
            if channel_name not in self.channels:
                self.log.error(
                    f"short_suffixes[{letter!r}] -> unknown channel "
                    f"{channel_name!r}; ignored",
                    source="ChannelMatcher")
                continue
            table[letter] = channel_name
        return table

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

    def matches_normalized(self, normalized, ignore_aliases=(),
                           enable_short_suffixes=False):
        """Every channel *normalized* matches, longest alias first.

        ``ignore_aliases`` are skipped: they belong to the whole set (see
        :func:`shared_keywords`) and are not evidence about one file.

        ``enable_short_suffixes`` additionally considers a whitelisted
        single-letter last token (``_d``, ``_b005``).  The caller turns it on per
        directory (see :func:`short_suffix_letters`), so a lone letter is never
        evidence on its own.  Such a match is appended last, so a real alias
        always wins the "first match" tie-break.
        """
        matches = []
        matched_channels = set()
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
            matched_channels.add(channel_name)

        if enable_short_suffixes and self.short_suffixes:
            short = self._short_suffix_match(normalized)
            if short is not None and short.channel not in matched_channels:
                matches.append(short)
        return matches

    def _short_suffix_match(self, normalized):
        """Match a whitelisted single-letter last token, or None.

        Only the *last* token counts, and only as a bare letter or letter plus a
        strength/resolution number (``d`` / ``b005`` / ``r100``).
        """
        tokens = normalized.split("_")
        if not tokens:
            return None
        found = _SHORT_TOKEN_RE.fullmatch(tokens[-1])
        if not found:
            return None
        channel_name = self.short_suffixes.get(found.group(1))
        if not channel_name:
            return None
        channel_data = self.channels.get(channel_name, {})
        start = len(normalized) - len(tokens[-1])
        return ChannelMatch(
            channel=channel_name,
            common_attr=channel_data.get("common_attr", ""),
            channel_type=channel_data.get("type", ""),
            alias=found.group(1),
            span=(start, len(normalized)),
        )

    def matches(self, stem, ignore_aliases=(), enable_short_suffixes=False):
        """Every channel *stem* matches, longest alias first."""
        return self.matches_normalized(normalize_stem(stem), ignore_aliases,
                                       enable_short_suffixes)

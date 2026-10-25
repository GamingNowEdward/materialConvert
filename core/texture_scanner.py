import json
import os
import re

from core.filename_match import (ChannelMatcher, normalize_stem, quality_key,
                                 shared_keywords, short_suffix_letters,
                                 token_matches)
from core.logger import get_logger

_SOURCE = "TextureScanner"


class TextureScanner:

    def __init__(self, config_path=None, logger=None, extra_aliases=None,
                 extra_ignores=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config",
                "texture_channels.json",
            )
        self.log = logger or get_logger()
        self.config = self._load_config(config_path)
        self.extensions = {
            ext.lower() for ext in self.config.get("extensions", [])
        }
        self.channels = self._with_extra_aliases(
            self.config.get("channels", {}), extra_aliases)
        #: File names carrying one of these tokens are artwork/previews, not
        #: textures: they are skipped entirely instead of reported as unparsed.
        self.ignore_keywords = {
            str(kw).lower() for kw in self.config.get("ignore_keywords", [])
        }
        #: Session tokens that must never be read as a channel marker (the
        #: manual counterpart of the set-wide common-token detection).
        self.extra_ignore_aliases = {
            normalize_stem(str(token)) for token in (extra_ignores or [])
        }
        # Filename matching lives in core.filename_match so the Colorspace name
        # driver matches names by exactly the same rules.
        self._matcher = ChannelMatcher(
            self.channels,
            short_suffixes=self.config.get("short_suffixes", {}),
            logger=self.log,
        )
        self.log.debug(
            f"TextureScanner initialized: {len(self.channels)} channel(s), "
            f"{len(self.extensions)} extension(s), "
            f"{len(self._matcher.aliases)} alias(es)",
            source=_SOURCE,
        )

    def _load_config(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self.log.error(f"Failed to load texture channel config {path}: {exc}", source=_SOURCE)
            raise

    @staticmethod
    def _with_extra_aliases(channels, extra_aliases):
        """Channel definitions with the session aliases applied.

        ``extra_aliases`` (from the UI) *replaces* a channel's configured alias
        list, matching ``ConfigLoader.get_texture_channels`` semantics.
        """
        if not extra_aliases:
            return channels
        merged = {name: dict(data) for name, data in channels.items()}
        for name, aliases in extra_aliases.items():
            if name in merged:
                merged[name]["aliases"] = list(aliases)
        return merged

    @staticmethod
    def _normalize(name):
        return normalize_stem(name)

    @staticmethod
    def _clean_base_name(name):
        name = re.sub(r"[\s_\-()]+", "_", name)
        return name.strip("_")

    def _noise_aliases(self, stems):
        """Alias tokens shared by most files of the directory.

        Such a token is a property of the whole texture set (part of the material
        name), not the marker of a single file's channel — e.g. every file of a
        set ending in ``_METALNESS``.  Only alias tokens can be noise, so the
        asset name itself is never stripped, and small directories return an
        empty set because "shared by most files" is meaningless there.
        """
        return shared_keywords(stems, self._matcher.aliases)

    def _mask_tokens(self, normalized, noise):
        """Blank out the *noise* alias tokens, keeping offsets aligned with the stem.

        Replacing a token with dots of the same length keeps the matcher offsets
        valid for the original filename, and a dot is neither a word character
        nor skipped by the matcher, so it also acts as a boundary.
        Returns ``(masked, spans)``.
        """
        chars = list(normalized)
        spans = []
        offset = 0
        for token in normalized.split("_"):
            length = len(token)
            if length and self._is_noise_token(token, noise):
                for index in range(offset, offset + length):
                    chars[index] = "."
                spans.append((offset, offset + length))
            offset += length + 1
        return "".join(chars), spans

    def _is_noise_token(self, token, noise):
        """Whether *token* is a set-wide alias or a manual ``Ignore`` entry.

        A manual entry need not be a configured alias (``g`` for Arroway's
        ``g025``), so it also matches as a bare token or with a glued number.
        """
        if self._matcher.alias_of_token(token) in noise:
            return True
        return any(token_matches(token, ignore)
                   for ignore in self.extra_ignore_aliases)

    @staticmethod
    def _strip_spans(text, spans):
        """Drop the given ``(start, end)`` ranges from *text*."""
        if not spans:
            return text
        drop = [False] * len(text)
        for start, end in spans:
            for index in range(max(0, start), min(len(text), end)):
                drop[index] = True
        return "".join(char for index, char in enumerate(text) if not drop[index])

    def _parse(self, stem, noise=(), enable_short_suffixes=False):
        normalized = self._normalize(stem)
        noise_spans = []
        if noise:
            normalized, noise_spans = self._mask_tokens(normalized, noise)

        matches = self._matcher.matches_normalized(
            normalized, ignore_aliases=noise,
            enable_short_suffixes=enable_short_suffixes)
        if not matches:
            return None

        # Every matched channel marker is stripped from the material name, not
        # just the first: a file like ``concrete_53_s050_g025`` carries both a
        # specular and a gloss token, and leaving one behind would split it off
        # into a material of its own.
        spans = [match.span for match in matches] + noise_spans
        base_name = self._clean_base_name(self._strip_spans(stem, spans))
        if not base_name:
            base_name = "Material"

        for match in matches:
            channel_data = self._matcher.channels.get(match.channel, {})
            options = {}
            if channel_data.get("invert"):
                options["invert"] = True
            if match.channel_type in ("normal", "bump"):
                options["mode"] = match.channel_type

            common_attr = match.common_attr
            if not common_attr:
                self.log.warn(f"Texture channel {match.channel} has no common_attr", source=_SOURCE)
                continue
            return match.channel, common_attr, base_name, options

        return None

    def scan(self, directory, recursive=False):
        """Scan a directory and group textures by material name.

        Non-recursive by default.  With ``recursive`` every subdirectory is
        scanned too; each directory is handled on its own (the common-token and
        single-letter decisions are per set) and the results are merged.
        """
        if not directory or not os.path.isdir(directory):
            self.log.warn(f"Texture scan skipped: invalid directory {directory!r}", source=_SOURCE)
            return {"materials": [], "unparsed": [], "conflicts": [], "conflict_materials": []}

        if not recursive:
            return self._scan_one(directory)

        results = [self._scan_one(path) for path in self._iter_scan_dirs(directory)]
        return self._merge_results(results)

    @staticmethod
    def _iter_scan_dirs(directory):
        """*directory* followed by every subdirectory (depth first, sorted)."""
        directories = [directory]
        for root, subdirs, _files in os.walk(directory):
            subdirs.sort()
            for name in subdirs:
                directories.append(os.path.join(root, name))
        return directories

    def _scan_one(self, directory):
        """Scan a single directory (non-recursive)."""
        materials = {}
        unparsed = []
        conflicts = []

        try:
            files = sorted(os.listdir(directory))
        except Exception as exc:
            self.log.error(f"Failed to list texture directory {directory}: {exc}", source=_SOURCE)
            return {"materials": [], "unparsed": [], "conflicts": [], "conflict_materials": []}

        self.log.debug(f"Scanning {len(files)} file(s) in {directory}", source=_SOURCE)

        candidates = []
        for filename in files:
            full_path = os.path.join(directory, filename)
            try:
                is_file = os.path.isfile(full_path)
            except Exception as exc:
                self.log.warn(f"Failed to inspect {full_path}: {exc}", source=_SOURCE)
                continue

            if not is_file:
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in self.extensions:
                self.log.debug(f"{filename}: extension {ext} ignored", source=_SOURCE)
                continue

            stem = os.path.splitext(filename)[0]
            if self._is_ignored(stem):
                self.log.debug(
                    f"{filename}: matches an ignore keyword; skipped", source=_SOURCE)
                continue

            candidates.append((filename, full_path, stem))

        stems = [stem for _filename, _path, stem in candidates]
        noise = self._noise_aliases(stems) | self.extra_ignore_aliases
        if noise:
            self.log.info(
                f"Ignoring common alias token(s) shared by the texture set: "
                f"{', '.join(sorted(noise))}",
                source=_SOURCE,
            )

        enable_short = len(short_suffix_letters(stems, self._matcher.short_suffixes)) >= 2
        parsed_files = self._parse_candidates(candidates, noise, enable_short)
        if noise and not any(parsed is not None for parsed in parsed_files):
            # Nothing resolved with the common tokens ignored, so they really were
            # the channel markers (e.g. a directory holding only metallic maps):
            # fall back to the plain behaviour.
            self.log.info(
                f"No channel resolved with {', '.join(sorted(noise))} ignored; "
                f"scanning without the common-token filter",
                source=_SOURCE,
            )
            parsed_files = self._parse_candidates(candidates, set(), enable_short)

        for (filename, full_path, stem), parsed in zip(candidates, parsed_files):
            if not parsed:
                self.log.debug(f"{filename}: no texture channel matched", source=_SOURCE)
                unparsed.append(full_path)
                continue

            channel_name, common_attr, base_name, options = parsed
            self.log.debug(
                f"{filename}: parsed as {channel_name} -> {common_attr} (material={base_name})",
                source=_SOURCE,
            )

            material = materials.setdefault(
                base_name,
                {
                    "name": base_name,
                    "channels": {},
                },
            )

            if common_attr in material["channels"]:
                kept = material["channels"][common_attr]
                kept_path = kept["path"]
                kept_stem = os.path.splitext(os.path.basename(kept_path))[0]
                if self._better(stem, channel_name, kept_stem, kept["channel"]):
                    # A higher bit depth / resolution or priority wins.
                    self._record_conflict(conflicts, base_name, common_attr, full_path, kept_path)
                    kept.update({"channel": channel_name, "path": full_path, "options": options})
                    self.log.warn(
                        f"Texture conflict for {base_name}/{common_attr}: keeping "
                        f"{full_path} over {kept_path} (higher bit depth/resolution/priority)",
                        source=_SOURCE,
                    )
                else:
                    self._record_conflict(conflicts, base_name, common_attr, kept_path, full_path)
                    self.log.warn(
                        f"Texture conflict for {base_name}/{common_attr}: "
                        f"{kept_path} vs {full_path}",
                        source=_SOURCE,
                    )
                continue

            material["channels"][common_attr] = {
                "channel": channel_name,
                "path": full_path,
                "options": options,
            }

        result = {
            "materials": list(materials.values()),
            "unparsed": unparsed,
            "conflicts": conflicts,
            "conflict_materials": sorted({item["material"] for item in conflicts}),
        }
        self.log.info(
            f"Texture scan finished: {len(result['materials'])} material(s), "
            f"{len(unparsed)} unparsed, {len(conflicts)} conflict(s)",
            source=_SOURCE,
        )
        return result

    def _merge_results(self, results):
        """Merge per-directory scans for a recursive scan."""
        materials = {}
        unparsed = []
        conflicts = []
        for result in results:
            unparsed.extend(result["unparsed"])
            for material in result["materials"]:
                target = materials.setdefault(
                    material["name"], {"name": material["name"], "channels": {}})
                for common_attr, data in material["channels"].items():
                    self._merge_channel(target, common_attr, data, conflicts)

        merged = {
            "materials": list(materials.values()),
            "unparsed": unparsed,
            "conflicts": conflicts,
            "conflict_materials": sorted({item["material"] for item in conflicts}),
        }
        self.log.info(
            f"Recursive texture scan finished: {len(merged['materials'])} material(s), "
            f"{len(unparsed)} unparsed, {len(conflicts)} conflict(s)",
            source=_SOURCE,
        )
        return merged

    def _merge_channel(self, material, common_attr, data, conflicts):
        """Merge one channel into a material, resolving duplicates like a scan."""
        existing = material["channels"].get(common_attr)
        if existing is None:
            material["channels"][common_attr] = data
            return

        existing_stem = os.path.splitext(os.path.basename(existing["path"]))[0]
        new_stem = os.path.splitext(os.path.basename(data["path"]))[0]
        if self._better(new_stem, data["channel"], existing_stem, existing["channel"]):
            self._record_conflict(conflicts, material["name"], common_attr,
                                  data["path"], existing["path"])
            material["channels"][common_attr] = data
        else:
            self._record_conflict(conflicts, material["name"], common_attr,
                                  existing["path"], data["path"])

    def _better(self, stem, channel, other_stem, other_channel):
        """Whether a candidate beats the current one for the same channel.

        Higher bit depth / resolution first, then the configured channel
        priority (e.g. Roughness over Glossiness), then the name order.
        """
        return (quality_key(stem), self._priority(channel)) > (
            quality_key(other_stem), self._priority(other_channel))

    def _priority(self, channel_name):
        return self.channels.get(channel_name, {}).get("priority", 0)

    def _is_ignored(self, stem):
        """Whether *stem* carries a configured ignore keyword (artwork/preview)."""
        if not self.ignore_keywords:
            return False
        return any(token in self.ignore_keywords
                   for token in normalize_stem(stem).split("_"))

    def _parse_candidates(self, candidates, noise, enable_short_suffixes=False):
        """Parse every candidate stem, ignoring the given common alias tokens."""
        return [self._parse(stem, noise, enable_short_suffixes)
                for _filename, _path, stem in candidates]

    @staticmethod
    def _record_conflict(conflicts, material_name, common_attr, kept_path, dropped_path):
        """Accumulate one channel conflict, keeping every candidate visible.

        ``kept_path`` is the file the scan will use, ``dropped_path`` the one it
        will not; the caller decides (a later candidate wins on higher bit depth
        / resolution or channel priority, otherwise the first file in name order
        wins).  ``dropped`` always mirrors ``candidates`` minus ``kept``, so the
        UI shows the real outcome instead of an arbitrary choice.
        """
        for item in conflicts:
            if item["material"] == material_name and item["common_attr"] == common_attr:
                for path in (dropped_path, kept_path):
                    if path not in item["candidates"]:
                        item["candidates"].append(path)
                item["kept"] = kept_path
                item["dropped"] = [path for path in item["candidates"] if path != kept_path]
                return
        conflicts.append({
            "material": material_name,
            "common_attr": common_attr,
            "existing": kept_path,
            "kept": kept_path,
            "candidates": [kept_path, dropped_path],
            "dropped": [dropped_path],
        })

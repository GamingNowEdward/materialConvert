import json
import os
import re

from core.filename_match import ChannelMatcher, normalize_stem, quality_key, shared_keywords
from core.logger import get_logger

_SOURCE = "TextureScanner"


class TextureScanner:

    def __init__(self, config_path=None, logger=None):
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
        self.channels = self.config.get("channels", {})
        # Filename matching lives in core.filename_match so the Colorspace name
        # driver matches names by exactly the same rules.
        self._matcher = ChannelMatcher(self.channels, logger=self.log)
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
    def _normalize(name):
        return normalize_stem(name)

    @staticmethod
    def _clean_base_name(name):
        name = re.sub(r"[\s_-]+", "_", name)
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
            if length and self._matcher.alias_of_token(token) in noise:
                for index in range(offset, offset + length):
                    chars[index] = "."
                spans.append((offset, offset + length))
            offset += length + 1
        return "".join(chars), spans

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

    def _parse(self, stem, noise=()):
        normalized = self._normalize(stem)
        noise_spans = []
        if noise:
            normalized, noise_spans = self._mask_tokens(normalized, noise)

        for match in self._matcher.matches_normalized(normalized, ignore_aliases=noise):
            channel_data = self._matcher.channels.get(match.channel, {})
            start, end = match.span
            base_name = self._clean_base_name(
                self._strip_spans(stem, [(start, end)] + noise_spans))
            if not base_name:
                base_name = "Material"

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

    def scan(self, directory):
        """Scan a directory (non-recursive) and group textures by material name."""
        materials = {}
        unparsed = []
        conflicts = []

        if not directory or not os.path.isdir(directory):
            self.log.warn(f"Texture scan skipped: invalid directory {directory!r}", source=_SOURCE)
            return {"materials": [], "unparsed": [], "conflicts": [], "conflict_materials": []}

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

            candidates.append((filename, full_path, os.path.splitext(filename)[0]))

        noise = self._noise_aliases([stem for _filename, _path, stem in candidates])
        if noise:
            self.log.info(
                f"Ignoring common alias token(s) shared by the texture set: "
                f"{', '.join(sorted(noise))}",
                source=_SOURCE,
            )

        parsed_files = self._parse_candidates(candidates, noise)
        if noise and not any(parsed is not None for parsed in parsed_files):
            # Nothing resolved with the common tokens ignored, so they really were
            # the channel markers (e.g. a directory holding only metallic maps):
            # fall back to the plain behaviour.
            self.log.info(
                f"No channel resolved with {', '.join(sorted(noise))} ignored; "
                f"scanning without the common-token filter",
                source=_SOURCE,
            )
            parsed_files = self._parse_candidates(candidates, set())

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
                if quality_key(stem) > quality_key(kept_stem):
                    # A higher bit depth / resolution wins, whatever the name order.
                    self._record_conflict(conflicts, base_name, common_attr, full_path, kept_path)
                    kept.update({"channel": channel_name, "path": full_path, "options": options})
                    self.log.warn(
                        f"Texture conflict for {base_name}/{common_attr}: keeping "
                        f"{full_path} over {kept_path} (higher bit depth/resolution)",
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

    def _parse_candidates(self, candidates, noise):
        """Parse every candidate stem, ignoring the given common alias tokens."""
        return [self._parse(stem, noise) for _filename, _path, stem in candidates]

    @staticmethod
    def _record_conflict(conflicts, material_name, common_attr, kept_path, dropped_path):
        """Accumulate one channel conflict, keeping every candidate visible.

        ``kept_path`` is the file the scan will use, ``dropped_path`` the one it
        will not; the caller decides (the first file in name order wins unless a
        later candidate has a higher bit depth or resolution).  ``dropped`` always
        mirrors ``candidates`` minus ``kept``, so the UI shows the real outcome
        instead of an arbitrary choice.
        """
        for item in conflicts:
            if item["material"] == material_name and item["common_attr"] == common_attr:
                if dropped_path not in item["candidates"]:
                    item["candidates"].append(dropped_path)
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

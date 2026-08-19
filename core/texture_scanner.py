import json
import os
import re


class TextureScanner:

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config",
                "texture_channels.json",
            )
        self.config = self._load_config(config_path)
        self.extensions = {
            ext.lower() for ext in self.config.get("extensions", [])
        }
        self.channels = self.config.get("channels", {})

    @staticmethod
    def _load_config(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _normalize(name):
        return re.sub(r"[- ]", "_", name.lower())

    @staticmethod
    def _clean_base_name(name):
        name = re.sub(r"[\s_-]+", "_", name)
        return name.strip("_")

    def _find_alias(self, normalized, alias):
        """Return (start, end) in normalized if alias is found.

        Priority:
        1. Exact token match (safe for short aliases).
        2. Substring match ignoring underscores, only for longer aliases,
           and only when the alias is bounded by non-alphanumeric characters.
        """
        tokens = normalized.split("_")
        if alias in tokens:
            idx = tokens.index(alias)
            start = sum(len(t) + 1 for t in tokens[:idx])
            return start, start + len(alias)

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

    def _parse(self, stem):
        normalized = self._normalize(stem)

        candidates = []
        for channel_name, channel_data in self.channels.items():
            for alias in channel_data.get("aliases", []):
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                candidates.append((channel_name, channel_data, alias_norm))

        candidates.sort(key=lambda item: len(item[2]), reverse=True)

        for channel_name, channel_data, alias_norm in candidates:
            found = self._find_alias(normalized, alias_norm)
            if not found:
                continue

            start, end = found
            base_name = self._clean_base_name(stem[:start] + stem[end:])
            if not base_name:
                base_name = "Material"

            options = {}
            if channel_data.get("invert"):
                options["invert"] = True
            channel_type = channel_data.get("type", "")
            if channel_type in ("normal", "bump"):
                options["mode"] = channel_type

            common_attr = channel_data.get("common_attr")
            if not common_attr:
                continue
            return channel_name, common_attr, base_name, options

        return None

    def scan(self, directory):
        """Scan a directory (non-recursive) and group textures by material name.

        Returns:
            {
                "materials": [
                    {
                        "name": str,
                        "channels": {
                        common_attr: {
                                "channel": str,
                                "path": str,
                                "options": dict,
                            }
                        }
                    }
                ],
                "unparsed": [full_path, ...],
                "conflicts": [dict, ...],
            }
        """
        materials = {}
        unparsed = []
        conflicts = []

        if not os.path.isdir(directory):
            return {"materials": [], "unparsed": [], "conflicts": []}

        for filename in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, filename)
            if not os.path.isfile(full_path):
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in self.extensions:
                continue

            stem = os.path.splitext(filename)[0]
            parsed = self._parse(stem)
            if not parsed:
                unparsed.append(full_path)
                continue

            channel_name, common_attr, base_name, options = parsed

            material = materials.setdefault(
                base_name,
                {
                    "name": base_name,
                    "channels": {},
                },
            )

            if common_attr in material["channels"]:
                conflicts.append(
                    {
                        "material": base_name,
                        "common_attr": common_attr,
                        "existing": material["channels"][common_attr]["path"],
                        "new": full_path,
                    }
                )
                continue

            material["channels"][common_attr] = {
                "channel": channel_name,
                "path": full_path,
                "options": options,
            }

        return {
            "materials": list(materials.values()),
            "unparsed": unparsed,
            "conflicts": conflicts,
        }

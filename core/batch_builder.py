from core.builder_context import BuilderContext
from core.material_builder import MaterialBuilder


class BatchBuilder:

    # texture_channels.json builder_key -> MaterialBuilder short key
    COMMON_TO_SHORT = {
        "baseColor": "color",
        "specularRoughness": "rough",
        "metallic": "metallic",
        "normal_bump": None,  # depends on normal/bump mode
        "displacementTexture": "disp",
        "opacity": "opacity",
        "emissionColor": "emission",
        "transmissionColor": "transmission",
        "fuzzColor": "sheen",
        "subsurfaceColor": "sss",
        "specularColor": "reflection",
    }

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.builder = MaterialBuilder(ctx)

    @classmethod
    def _short_key(cls, builder_key, options):
        if builder_key == "normal_bump":
            return "nrm" if options.get("mode") == "normal" else "bump"
        return cls.COMMON_TO_SHORT.get(builder_key, builder_key)

    def build_material(self, node_type, material, use_full_chain=True, use_qss=True):
        """Build one material from a scanner material dict.

        material = {
            "name": str,
            "channels": {
                builder_key: {
                    "channel": str,
                    "path": str,
                    "options": dict,
                }
            }
        }
        """
        input_paths = {}
        channel_options = {}

        for builder_key, data in material.get("channels", {}).items():
            short_key = self._short_key(builder_key, data.get("options", {}))
            if not short_key:
                continue
            input_paths[short_key] = data["path"]
            if data.get("options"):
                channel_options[short_key] = dict(data["options"])

        use_disp = "disp" in input_paths
        use_sss = "sss" in input_paths

        return self.builder.build(
            node_type,
            material["name"],
            input_paths,
            use_nrm=True,
            use_sss=use_sss,
            use_disp=use_disp,
            use_qss=use_qss,
            use_full_chain=use_full_chain,
            channel_options=channel_options,
        )

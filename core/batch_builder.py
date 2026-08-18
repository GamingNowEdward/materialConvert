from core.builder_context import BuilderContext
from core.material_builder import MaterialBuilder


class BatchBuilder:

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx
        self.builder = MaterialBuilder(ctx)

    def build_material(self, node_type, material, use_full_chain=True, use_qss=True):
        """Build one material from a scanner material dict.

        material = {
            "name": str,
            "channels": {
                common_attr: {
                    "channel": str,
                    "path": str,
                    "options": dict,
                }
            }
        }
        """
        input_paths = {}
        channel_options = {}

        for common_attr, data in material.get("channels", {}).items():
            input_paths[common_attr] = data["path"]
            if data.get("options"):
                channel_options[common_attr] = dict(data["options"])

        use_disp = "displacementTexture" in input_paths
        use_sss = "subsurfaceColor" in input_paths

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

import maya.cmds as cmds

from core.logger import get_logger
from core.node_utils import RENDERER_SHORT, P2D_CONNECTIONS
from core.results import TransferOutcome

_SOURCE = "BumpConverter"

#: String attribute stamped on file nodes materialized by this converter.
#: It records which legacy node the file belongs to, so reuse never depends on
#: guessing ownership from the node name alone.
_EMBEDDED_MARKER = "mcEmbeddedSource"


class BumpConverter:

    def __init__(self, config, utils, logger=None):
        self.config = config
        self.utils = utils
        self.log = logger or get_logger()
        self._file_index = None
        self._bn_type_nodes = None

    def reset_index(self):
        """Drop the batch-scoped scene indexes (``file`` / bump-normal nodes)."""
        self._file_index = None
        self._bn_type_nodes = None

    def _bn_nodes(self):
        """Batch-scoped list of all configured bump/normal nodes in the scene."""
        if self._bn_type_nodes is None:
            nodes = []
            for node_type in self.config.get_all_bn_types():
                try:
                    nodes.extend(cmds.ls(type=node_type) or [])
                except Exception as exc:
                    self.log.warn(
                        f"Failed to list bump/normal nodes of type {node_type}: {exc}",
                        source=_SOURCE,
                    )
            self._bn_type_nodes = nodes
        return self._bn_type_nodes

    def convert(self, source_mat, target_mat, source_renderer, target_renderer):
        """Convert bump/normal.

        Returns a :class:`core.results.TransferOutcome`; ``ok`` False on a
        critical conversion step.  Object-space normal maps that the target
        cannot express are reported through ``issues`` instead of silently
        becoming tangent-space maps.
        """
        src_bn_config = self.config.get_bump_normal_config(source_renderer)
        tgt_bn_config = self.config.get_bump_normal_config(target_renderer)

        if not src_bn_config or not tgt_bn_config:
            self.log.skip(
                f"Bump/Normal conversion skipped: no config "
                f"(src={source_renderer}, tgt={target_renderer})",
                source=_SOURCE,
                nodes=(source_mat, target_mat),
            )
            return TransferOutcome()

        src_bn_info, collect_ok = self._collect(source_mat, src_bn_config)
        if not collect_ok:
            self.log.error(
                f"Bump/Normal collection failed for {source_mat}",
                source=_SOURCE, nodes=(source_mat,),
            )
            return TransferOutcome(
                ok=False,
                critical=[f"failed to collect bump/normal data from {source_mat}"])
        if not src_bn_info:
            self.log.skip(f"No source bump/normal data found on {source_mat}", source=_SOURCE, nodes=(source_mat,))
            return TransferOutcome()

        bump_info = src_bn_info.get("bump")
        normal_info = src_bn_info.get("normal")

        info = bump_info or normal_info
        if not info:
            self.log.skip(f"No usable bump/normal mapping collected from {source_mat}", source=_SOURCE, nodes=(source_mat,))
            return TransferOutcome()

        node = info.pop("bn_node", None)
        base_name = node if node else source_mat
        is_normal_mode = info.get("is_normal", False)
        tgt_mapping = tgt_bn_config.normal if is_normal_mode else tgt_bn_config.bump

        return self._do_convert(
            info, target_mat, tgt_mapping,
            target_renderer, is_normal=is_normal_mode, source_name=base_name
        )

    def reuse_existing(self, source_mat, new_mat, source_renderer):
        """Same-renderer path: reuse the existing bump/normal node.

        Returns a :class:`core.results.TransferOutcome`.
        """
        src_bn_config = self.config.get_bump_normal_config(source_renderer)
        if not src_bn_config:
            self.log.skip(f"No bump/normal config for source renderer {source_renderer}", source=_SOURCE, nodes=(source_mat, new_mat))
            return TransferOutcome()

        try:
            source_type = self.utils.identify_node_type(source_mat, logger=self.log)
        except Exception as exc:
            self.log.warn(f"Failed to identify source material {source_mat}: {exc}", source=_SOURCE, nodes=(source_mat,))
            return TransferOutcome(ok=False, critical=[f"failed to identify {source_mat}: {exc}"])
        src_mat_config = self.config.get_material_config(source_type)
        if not src_mat_config:
            self.log.warn(f"No material config for {source_type}", source=_SOURCE, nodes=(source_mat,))
            return TransferOutcome(ok=False, critical=[f"no material config for {source_type}"])
        src_bump_attr = src_mat_config.attr_map.get("normal_bump", "")
        if not src_bump_attr:
            self.log.skip(f"Source material {source_mat} has no normal_bump mapping", source=_SOURCE, nodes=(source_mat,))
            return TransferOutcome()

        try:
            target_type = self.utils.identify_node_type(new_mat, logger=self.log)
        except Exception as exc:
            self.log.warn(f"Failed to identify target material {new_mat}: {exc}", source=_SOURCE, nodes=(new_mat,))
            return TransferOutcome(ok=False, critical=[f"failed to identify {new_mat}: {exc}"])
        new_mat_config = self.config.get_material_config(target_type)
        if not new_mat_config:
            self.log.warn(f"No material config for {target_type}", source=_SOURCE, nodes=(new_mat,))
            return TransferOutcome(ok=False, critical=[f"no material config for {target_type}"])
        new_bump_attr = new_mat_config.attr_map.get("normal_bump", "")
        if not new_bump_attr:
            self.log.skip(f"Target material {new_mat} has no normal_bump mapping", source=_SOURCE, nodes=(new_mat,))
            return TransferOutcome()

        try:
            conns = cmds.listConnections(f"{source_mat}.{src_bump_attr}", source=True, destination=False) or []
            if not conns:
                self.log.skip(f"No source bump connection on {source_mat}.{src_bump_attr}", source=_SOURCE, nodes=(source_mat,))
                return TransferOutcome()
            src_node = conns[0]
            out_attr = self._resolve_source_output(src_node, src_bn_config.bump.output)
            cmds.connectAttr(f"{src_node}.{out_attr}",
                             f"{new_mat}.{new_bump_attr}", force=True)
            self.log.info(
                f"Bump/Normal: reconnected existing {src_node} -> {new_mat}.{new_bump_attr}",
                source=_SOURCE,
                nodes=(src_node, new_mat),
            )
            return TransferOutcome()
        except Exception as exc:
            self.log.warn(f"Bump/Normal reuse failed for {source_mat} -> {new_mat}: {exc}", source=_SOURCE, nodes=(source_mat, new_mat))
            return TransferOutcome(ok=False, critical=[f"bump/normal reuse failed: {exc}"])

    def _resolve_source_output(self, src_node, fallback_attr):
        """Output attribute of an existing bump/normal node.

        Shared types and standard nodes expose the renderer's bump-segment
        output, but legacy nodes such as ``RedshiftNormalMap`` expose a
        different output (``outDisplacementVector``). The actual node type is
        resolved first and its configured output is used when available.
        """
        try:
            src_type = cmds.nodeType(src_node)
        except Exception as exc:
            self.log.warn(
                f"Failed to identify source bump/normal node {src_node}: {exc}",
                source=_SOURCE, nodes=(src_node,),
            )
            return fallback_attr
        _, mapping = self.config.find_bn_renderer(src_type)
        if mapping is not None and mapping.output:
            return mapping.output
        return fallback_attr

    def _collect(self, source_mat, src_bn_config):
        result = {}
        ok = True

        standalone_segments = []
        for key, seg in (("bump", src_bn_config.bump), ("normal", src_bn_config.normal)):
            if seg is None:
                continue
            if seg.is_material_attribute:
                data = self._read_material_bn(source_mat, seg)
                if data and not data["should_skip"]:
                    result[key] = {
                        "scale": data["scale_val"],
                        "input_plug": data["input_plug"],
                        "is_normal": key == "normal",
                        "normal_space": data.get("normal_space"),
                    }
                else:
                    self.log.debug(f"Source {key} material attribute skipped on {source_mat}", source=_SOURCE, nodes=(source_mat,))
            else:
                standalone_segments.append((key, seg))

        if standalone_segments:
            bn_node = self._find_bn_node(source_mat)
            if bn_node is None:
                self.log.debug(f"No bump/normal node found on {source_mat}", source=_SOURCE, nodes=(source_mat,))
            for key, seg in standalone_segments:
                data, seg_ok = self._collect_node(bn_node, seg, key)
                if not seg_ok:
                    ok = False
                if data:
                    result[key] = data

        self.log.debug(
            f"Bump/Normal collection result for {source_mat}: {sorted(result.keys())}",
            source=_SOURCE,
            nodes=(source_mat,),
        )
        return result, ok

    def _read_material_bn(self, source_mat, bn_mapping):
        scale_attr = bn_mapping.scale
        input_attr = bn_mapping.input

        scale_val = None
        if scale_attr:
            try:
                scale_val = cmds.getAttr(f"{source_mat}.{scale_attr}")
                self.log.debug(f"Read {source_mat}.{scale_attr} = {scale_val!r}", source=_SOURCE, nodes=(source_mat,))
            except Exception as exc:
                self.log.warn(f"Failed to read scale [{scale_attr}] on {source_mat}: {exc}", source=_SOURCE, nodes=(source_mat,))

        input_plug = None
        if input_attr:
            try:
                conns = cmds.listConnections(f"{source_mat}.{input_attr}", plugs=True, source=True) or []
                if conns:
                    input_plug = conns[0]
                    self.log.debug(f"Read bump/normal input on {source_mat}.{input_attr}: {input_plug}", source=_SOURCE, nodes=(source_mat, self.utils.node_name_from_plug(input_plug)))
                else:
                    self.log.debug(f"No bump/normal input connected to {source_mat}.{input_attr}", source=_SOURCE, nodes=(source_mat,))
            except Exception as exc:
                self.log.warn(f"Failed to read bump/normal input on {source_mat}.{input_attr}: {exc}", source=_SOURCE, nodes=(source_mat,))

        should_skip = False
        normal_space = None
        if bn_mapping.is_normal:
            try:
                actual = cmds.getAttr(f"{source_mat}.{bn_mapping.is_normal}")
                if not bn_mapping.matches_mode_value(actual):
                    should_skip = True
                    self.log.debug(
                        f"{source_mat}.{bn_mapping.is_normal}={actual!r} does not match "
                        f"{bn_mapping.is_normal_value!r}; skipping",
                        source=_SOURCE,
                        nodes=(source_mat,),
                    )
                else:
                    normal_space = bn_mapping.space_for_value(actual)
            except Exception as exc:
                self.log.warn(f"Failed to read {source_mat}.{bn_mapping.is_normal}: {exc}", source=_SOURCE, nodes=(source_mat,))

        return {
            "scale_val": scale_val,
            "input_plug": input_plug,
            "should_skip": should_skip,
            "normal_space": normal_space,
        }

    def _collect_node(self, bn_node, bn_mapping, mode):
        if bn_node is None:
            return None, True

        node_actual_type = cmds.nodeType(bn_node)
        bn_renderer, bn_cfg = self.config.find_bn_renderer(node_actual_type)

        if bn_cfg is not None and bn_cfg.path:
            return self._collect_embedded_path_node(bn_node, bn_cfg)

        is_normal, normal_space = self._detect_bn_modes(
            bn_node, node_actual_type, bn_renderer, mode, mapping=bn_cfg)
        scale_val = self._read_bn_attrs(bn_node, bn_cfg, "scale")
        input_plug = self._read_bn_attrs(bn_node, bn_cfg, "input", is_connection=True)

        self.log.debug(
            f"Collected bump/normal node {bn_node}: type={node_actual_type}, "
            f"renderer={bn_renderer}, is_normal={is_normal}, space={normal_space}",
            source=_SOURCE,
            nodes=(bn_node,),
        )
        return {
            "bn_node": bn_node,
            "scale": scale_val,
            "input_plug": input_plug,
            "is_normal": is_normal,
            "normal_space": normal_space,
        }, True

    def _collect_embedded_path_node(self, bn_node, bn_cfg):
        """Collect a legacy node whose texture path is stored inside the node.

        ``RedshiftNormalMap`` keeps the bitmap path in ``tex0`` and has no
        upstream connection, so the path is materialized as a Maya ``file`` node
        (plus a ``place2dTexture``) whose output becomes the generic
        ``input_plug``; downstream conversion logic is left untouched.

        Returns ``(data, ok)``: ``ok=False`` marks a critical materialization
        failure so the caller fails the conversion instead of silently skipping
        it.
        """
        try:
            path = cmds.getAttr(f"{bn_node}.{bn_cfg.path}")
        except Exception as exc:
            self.log.error(
                f"Failed to read embedded texture path {bn_node}.{bn_cfg.path}: {exc}",
                source=_SOURCE, nodes=(bn_node,),
            )
            return None, False

        if not path:
            self.log.skip(
                f"{bn_node} has an empty embedded texture path ({bn_cfg.path}); skipped",
                source=_SOURCE, nodes=(bn_node,),
            )
            return None, True

        file_node, ok = self._build_file_from_path(bn_node, path, bn_cfg)
        if file_node is None:
            return None, ok

        scale_val = self._read_bn_attrs(bn_node, bn_cfg, "scale")
        file_source = bn_cfg.file_source or "outColor"
        input_plug = f"{file_node}.{file_source}"

        self.log.debug(
            f"Collected embedded-path node {bn_node}: path={path!r}, "
            f"file={file_node}, is_normal=True",
            source=_SOURCE, nodes=(bn_node, file_node),
        )
        return {
            "bn_node": bn_node,
            "scale": scale_val,
            "input_plug": input_plug,
            "is_normal": True,
            # The legacy node has no space switch; its normal maps are tangent
            # space by convention.
            "normal_space": "tangent",
        }, True

    def _build_file_from_path(self, bn_node, path, bn_cfg):
        """Materialize an embedded texture path as a ``file`` node.

        Returns ``(file_node, ok)``. ``file_node`` is ``None`` when
        materialization failed and ``ok`` is False for critical failures (node
        creation, missing/unusable place2dTexture, path write, or any
        place2dTexture connection) so incomplete wiring never masquerades as a
        successful conversion. Nodes created before the failure are left in the
        scene (old nodes are never deleted) and stay tagged, so a later retry can
        repair their UV chain instead of duplicating them.
        """
        existing = self._find_existing_embedded_file(bn_node, path)
        if existing is not None:
            self.log.debug(
                f"Reusing existing file node {existing} for {bn_node}",
                source=_SOURCE, nodes=(bn_node, existing),
            )
            return existing, True

        p2d = self._find_place2d(bn_node)
        if p2d is None:
            p2d = self._create_place2d(bn_node)
        if p2d is None:
            # Without a place2dTexture the file node has no UV source: that is a
            # critical materialization failure, not a cosmetic one.
            self.log.error(
                f"Could not create or reuse a place2dTexture for {bn_node}; "
                f"refusing to build an incomplete normal chain",
                source=_SOURCE, nodes=(bn_node,),
            )
            return None, False

        try:
            file_node = cmds.shadingNode("file", asTexture=True, name="tex_" + bn_node)
        except Exception as exc:
            self.log.error(
                f"Failed to create file node for {bn_node}: {exc}",
                source=_SOURCE, nodes=(bn_node,),
            )
            return None, False
        self.log.debug(f"Created file node {file_node} for {bn_node}", source=_SOURCE, nodes=(file_node,))
        self._tag_embedded_file(file_node, bn_node)
        if self._file_index is not None and file_node not in self._file_index:
            # Keep the batch-scoped index fresh: the same legacy node is collected
            # once per bump/normal segment, and the second pass must reuse this
            # node instead of materializing a duplicate.
            self._file_index.append(file_node)

        failed = False
        try:
            cmds.setAttr(f"{file_node}.fileTextureName", path, type="string")
        except Exception as exc:
            failed = True
            self.log.error(
                f"Failed to set {file_node}.fileTextureName={path!r}: {exc}",
                source=_SOURCE, nodes=(file_node,),
            )

        for src_attr, dst_attr in P2D_CONNECTIONS:
            try:
                if cmds.isConnected(f"{p2d}.{src_attr}", f"{file_node}.{dst_attr}"):
                    continue
                cmds.connectAttr(f"{p2d}.{src_attr}", f"{file_node}.{dst_attr}", force=True)
            except Exception as exc:
                failed = True
                self.log.error(
                    f"Failed to connect {p2d}.{src_attr} -> {file_node}.{dst_attr}: {exc}",
                    source=_SOURCE, nodes=(p2d, file_node),
                )

        if failed:
            return None, False
        return file_node, True

    def _file_nodes(self):
        """Batch-scoped list of ``file`` nodes (invalidated by ``reset_index``)."""
        if self._file_index is None:
            try:
                self._file_index = list(cmds.ls(type="file") or [])
            except Exception as exc:
                self.log.warn(f"Failed to list file nodes: {exc}", source=_SOURCE)
                self._file_index = []
        return self._file_index

    def _tag_embedded_file(self, file_node, bn_node):
        """Record ownership on the materialized file node (best effort)."""
        try:
            if not cmds.attributeQuery(_EMBEDDED_MARKER, node=file_node, exists=True):
                cmds.addAttr(file_node, longName=_EMBEDDED_MARKER, dataType="string")
            cmds.setAttr(f"{file_node}.{_EMBEDDED_MARKER}", bn_node, type="string")
        except Exception as exc:
            self.log.warn(
                f"Failed to tag {file_node} with {_EMBEDDED_MARKER}: {exc}; "
                f"reuse falls back to name + path matching",
                source=_SOURCE, nodes=(file_node,),
            )

    def _embedded_source_of(self, file_node):
        try:
            if not cmds.attributeQuery(_EMBEDDED_MARKER, node=file_node, exists=True):
                return None
            return cmds.getAttr(f"{file_node}.{_EMBEDDED_MARKER}") or None
        except Exception as exc:
            self.log.warn(
                f"Failed to read {_EMBEDDED_MARKER} on {file_node}: {exc}",
                source=_SOURCE, nodes=(file_node,),
            )
            return None

    def _uv_chain_complete(self, file_node):
        """Every P2D-driven input of *file_node* is fed by a place2dTexture."""
        for _src_attr, dst_attr in P2D_CONNECTIONS:
            try:
                conns = cmds.listConnections(
                    f"{file_node}.{dst_attr}", source=True, destination=False,
                    plugs=True) or []
            except Exception as exc:
                self.log.warn(
                    f"Failed to query {file_node}.{dst_attr}: {exc}",
                    source=_SOURCE, nodes=(file_node,),
                )
                return False
            if not conns:
                self.log.debug(
                    f"{file_node}.{dst_attr} has no UV source; chain incomplete",
                    source=_SOURCE, nodes=(file_node,),
                )
                return False
            node = conns[0].split(".", 1)[0]
            try:
                if cmds.nodeType(node) != "place2dTexture":
                    return False
            except Exception as exc:
                self.log.warn(
                    f"Failed to identify UV node {node}: {exc}",
                    source=_SOURCE, nodes=(node,),
                )
                return False
        return True

    def _repair_uv_chain(self, file_node, bn_node):
        """Reconnect a previously failed file node to a place2dTexture."""
        p2d = self._find_place2d(bn_node) or self._find_place2d(file_node)
        if p2d is None:
            p2d = self._create_place2d(bn_node)
        if p2d is None:
            return False

        repaired = True
        for src_attr, dst_attr in P2D_CONNECTIONS:
            try:
                if cmds.isConnected(f"{p2d}.{src_attr}", f"{file_node}.{dst_attr}"):
                    continue
                cmds.connectAttr(f"{p2d}.{src_attr}", f"{file_node}.{dst_attr}", force=True)
            except Exception as exc:
                repaired = False
                self.log.warn(
                    f"Failed to repair {p2d}.{src_attr} -> {file_node}.{dst_attr}: {exc}",
                    source=_SOURCE, nodes=(p2d, file_node),
                )
        if repaired:
            self.log.info(
                f"Repaired UV chain for {file_node} using {p2d}",
                source=_SOURCE, nodes=(file_node, p2d),
            )
        return repaired

    def _find_existing_embedded_file(self, bn_node, path):
        """Reusable file node for *bn_node* + *path*, or None.

        Reuse requires a complete P2D chain and unambiguous ownership: a node
        tagged with this legacy source wins, an untagged node only qualifies when
        its name prefix, path and UV chain all match (legacy scenes).  A tagged
        node with a broken chain is repaired instead of being reused as-is.
        """
        prefix = "tex_" + bn_node
        for node in self._file_nodes():
            if not (node == prefix or (node.startswith(prefix)
                                       and node[len(prefix):].isdigit())):
                continue
            try:
                if cmds.getAttr(f"{node}.fileTextureName") != path:
                    continue
            except Exception as exc:
                self.log.warn(
                    f"Failed to read {node}.fileTextureName: {exc}",
                    source=_SOURCE, nodes=(node,),
                )
                continue

            tagged_source = self._embedded_source_of(node)
            if tagged_source is not None:
                if tagged_source != bn_node:
                    self.log.debug(
                        f"File node {node} belongs to {tagged_source}, not {bn_node}",
                        source=_SOURCE, nodes=(node, bn_node),
                    )
                    continue
                if self._uv_chain_complete(node):
                    return node
                if self._repair_uv_chain(node, bn_node):
                    return node
                self.log.warn(
                    f"Reusable file node {node} has an unrepairable UV chain; "
                    f"a new node will be created",
                    source=_SOURCE, nodes=(node,),
                )
                continue

            if self._uv_chain_complete(node):
                self.log.debug(
                    f"Reusing untagged file node {node} (name + path + UV chain match)",
                    source=_SOURCE, nodes=(node,),
                )
                return node
            self.log.debug(
                f"Untagged file node {node} has an incomplete UV chain; not reused",
                source=_SOURCE, nodes=(node,),
            )
        return None

    def _find_place2d(self, bn_node):
        try:
            conns = cmds.listConnections(f"{bn_node}.uvCoord", source=True, plugs=True) or []
        except Exception as exc:
            self.log.warn(
                f"Failed to query uvCoord upstream on {bn_node}: {exc}",
                source=_SOURCE, nodes=(bn_node,),
            )
            return None
        for conn in conns:
            node = conn.split(".", 1)[0]
            try:
                if cmds.nodeType(node) == "place2dTexture":
                    self.log.debug(
                        f"Reusing existing place2dTexture {node} from {bn_node}",
                        source=_SOURCE, nodes=(bn_node, node),
                    )
                    return node
            except Exception as exc:
                self.log.warn(
                    f"Failed to identify node type for {node}: {exc}",
                    source=_SOURCE, nodes=(node,),
                )
        return None

    def _create_place2d(self, bn_node):
        try:
            p2d = cmds.shadingNode("place2dTexture", asUtility=True, name="p2d_" + bn_node)
        except Exception as exc:
            self.log.error(
                f"Failed to create place2dTexture for {bn_node}: {exc}",
                source=_SOURCE, nodes=(bn_node,),
            )
            return None
        self.log.debug(f"Created place2dTexture {p2d} for {bn_node}", source=_SOURCE, nodes=(bn_node, p2d))
        return p2d

    def _find_bn_node(self, material):
        try:
            material_type = self.utils.identify_node_type(material, logger=self.log)
        except Exception as exc:
            self.log.warn(f"Failed to identify material {material}: {exc}", source=_SOURCE, nodes=(material,))
            return None

        common_config = self.config.get_material_config(material_type)
        if common_config:
            bump_attr_name = common_config.attr_map.get("normal_bump", "")
            if bump_attr_name:
                try:
                    conns = cmds.listConnections(f"{material}.{bump_attr_name}",
                                                 source=True, destination=False) or []
                    for conn in conns:
                        if cmds.nodeType(conn) in self.config.get_all_bn_types():
                            self.log.debug(f"Found bump/normal node {conn} on {material}.{bump_attr_name}", source=_SOURCE, nodes=(conn, material))
                            return conn
                except Exception as exc:
                    self.log.warn(
                        f"Failed to list bump/normal connections on {material}.{bump_attr_name}: {exc}",
                        source=_SOURCE,
                        nodes=(material,),
                    )

        all_nodes = self._bn_nodes()

        self.log.debug(f"Scanning {len(all_nodes)} bump/normal node(s) for {material}", source=_SOURCE, nodes=tuple(all_nodes))
        for node in all_nodes:
            try:
                node_type = cmds.nodeType(node)
            except Exception as exc:
                self.log.warn(f"Failed to identify node type for {node}: {exc}", source=_SOURCE, nodes=(node,))
                continue
            _, node_cfg = self.config.find_bn_renderer(node_type)
            if node_cfg is None or not node_cfg.output:
                continue
            try:
                out_conns = cmds.listConnections(f"{node}.{node_cfg.output}",
                                                 destination=True, source=False) or []
            except Exception as exc:
                self.log.warn(
                    f"Failed to list outputs for {node}.{node_cfg.output}: {exc}",
                    source=_SOURCE,
                    nodes=(node,),
                )
                continue
            for conn in out_conns:
                if conn == material:
                    self.log.debug(f"Found bump/normal node {node} feeding {material}", source=_SOURCE, nodes=(node, material))
                    return node

        self.log.debug(f"No bump/normal node found for {material}", source=_SOURCE, nodes=(material,))
        return None

    def _detect_bn_modes(self, bn_node, node_actual_type, bn_renderer, default_mode, mapping=None):
        """``(is_normal, space)`` for a bump/normal node.

        ``space`` is ``"tangent"`` / ``"object"`` when the renderer encodes the
        normal space on the mode switch, otherwise None (unknown/not applicable).
        """
        if mapping is not None and mapping.path:
            self.log.debug(
                f"{node_actual_type} uses an embedded texture path; treated as normal",
                source=_SOURCE,
                nodes=(bn_node,),
            )
            return True, "tangent"
        if bn_renderer is None:
            self.log.warn(
                f"Unknown bump/normal node type {node_actual_type}; defaulting mode to "
                f"{'normal' if default_mode == 'normal' else 'bump'}",
                source=_SOURCE,
                nodes=(bn_node,),
            )
            return default_mode == "normal", None

        r_config = self.config.get_bump_normal_config(bn_renderer)
        bump_type = r_config.bump.node_type if r_config.bump else ""
        normal_type = r_config.normal.node_type if r_config.normal else ""

        if normal_type and normal_type == node_actual_type and normal_type != bump_type:
            return True, None
        if bump_type and bump_type == node_actual_type and bump_type != normal_type:
            return False, None
        if r_config.bump and r_config.bump.is_normal:
            try:
                actual = cmds.getAttr(f"{bn_node}.{r_config.bump.is_normal}")
            except Exception as exc:
                self.log.warn(f"Failed to read {bn_node}.{r_config.bump.is_normal}: {exc}", source=_SOURCE, nodes=(bn_node,))
                return default_mode == "normal", None

            if r_config.normal and r_config.normal.matches_mode_value(actual):
                return True, r_config.normal.space_for_value(actual)
            if r_config.bump.matches_mode_value(actual):
                return False, None
        return default_mode == "normal", None

    def _read_bn_attrs(self, bn_node, bn_cfg, attr_name, is_connection=False):
        if bn_cfg is None:
            return None
        attr_val = getattr(bn_cfg, attr_name, None)
        if not attr_val:
            return None
        try:
            if is_connection:
                conns = cmds.listConnections(f"{bn_node}.{attr_val}", plugs=True, source=True) or []
                result = conns[0] if conns else None
                self.log.debug(f"Read connection {bn_node}.{attr_val}: {result}", source=_SOURCE, nodes=(bn_node,))
                return result
            result = cmds.getAttr(f"{bn_node}.{attr_val}")
            self.log.debug(f"Read {bn_node}.{attr_val} = {result!r}", source=_SOURCE, nodes=(bn_node,))
            return result
        except Exception as exc:
            self.log.warn(f"Failed to read {bn_node}.{attr_val}: {exc}", source=_SOURCE, nodes=(bn_node,))
        return None

    def _do_convert(self, bn_info, target_mat, tgt_mapping,
                    target_renderer, is_normal, source_name):
        outcome = TransferOutcome()
        if not tgt_mapping:
            self.log.skip(
                f"Target renderer {target_renderer} has no "
                f"{'normal' if is_normal else 'bump'} mapping",
                source=_SOURCE,
                nodes=(target_mat,),
            )
            return outcome

        input_plug = bn_info.get("input_plug")
        if not input_plug:
            self.log.skip("Bump/Normal conversion skipped: no input connection", source=_SOURCE, nodes=(target_mat,))
            return outcome

        source_space = bn_info.get("normal_space")
        if is_normal and source_space == "object" and not tgt_mapping.supported_spaces:
            outcome.issues.append(
                f"{target_renderer}: object-space normal not representable on this "
                f"target; its default normal space is used")
            self.log.warn(
                f"Target {target_renderer} cannot express object-space normals; "
                f"the map will be interpreted in the renderer default space",
                source=_SOURCE, nodes=(target_mat,),
            )

        if tgt_mapping.is_material_attribute:
            self._convert_to_material(bn_info, target_mat, tgt_mapping, input_plug,
                                      outcome, source_space)
        else:
            self._convert_to_node(bn_info, target_mat, tgt_mapping,
                                  target_renderer, is_normal, source_name, input_plug,
                                  outcome, source_space)
        return outcome

    def _apply_normal_mode(self, node, mapping, source_space, outcome):
        """Write the mode switch while preserving the source normal space."""
        if not mapping.is_normal:
            return
        value = mapping.mode_value_for_space(source_space)
        if value is None:
            value = mapping.effective_mode_value()
            if value is None:
                return
            if source_space:
                outcome.issues.append(
                    f"{node}: {source_space}-space normal not supported by this "
                    f"target; wrote mode {value!r}")
        try:
            cmds.setAttr(f"{node}.{mapping.is_normal}", value)
            self.log.debug(
                f"Set {node}.{mapping.is_normal} = {value!r} (space={source_space or 'unknown'})",
                source=_SOURCE,
                nodes=(node,),
            )
        except Exception as exc:
            outcome.ok = False
            outcome.critical.append(f"failed to set mode on {node}: {exc}")
            self.log.warn(f"Failed to set is_normal on {node}: {exc}", source=_SOURCE, nodes=(node,))

    def _convert_to_material(self, bn_info, target_mat, tgt_mapping, input_plug,
                             outcome, source_space):
        scale_attr = tgt_mapping.scale
        input_attr = tgt_mapping.input

        if scale_attr and bn_info.get("scale") is not None:
            try:
                cmds.setAttr(f"{target_mat}.{scale_attr}", bn_info["scale"])
                self.log.debug(f"Set {target_mat}.{scale_attr} = {bn_info['scale']!r}", source=_SOURCE, nodes=(target_mat,))
            except Exception as exc:
                outcome.ok = False
                outcome.critical.append(f"failed to set scale {scale_attr} on {target_mat}: {exc}")
                self.log.warn(f"Failed to set scale [{scale_attr}] on {target_mat}: {exc}", source=_SOURCE, nodes=(target_mat,))

        if input_attr:
            if self.utils.smart_connect(input_plug, f"{target_mat}.{input_attr}", logger=self.log):
                self.log.debug(f"Connected bump/normal input {input_plug} -> {target_mat}.{input_attr}", source=_SOURCE, nodes=(self.utils.node_name_from_plug(input_plug), target_mat))
            else:
                outcome.ok = False
                outcome.critical.append(f"failed to connect {input_plug} -> {target_mat}.{input_attr}")
                self.log.warn(f"Failed to connect {input_plug} -> {target_mat}.{input_attr}", source=_SOURCE, nodes=(self.utils.node_name_from_plug(input_plug), target_mat))

        self._apply_normal_mode(target_mat, tgt_mapping, source_space, outcome)

        if outcome.ok:
            self.log.info("Bump/Normal: converted to material attributes", source=_SOURCE, nodes=(target_mat,))
        else:
            self.log.warn("Bump/Normal: material-attribute conversion incomplete", source=_SOURCE, nodes=(target_mat,))

    def _convert_to_node(self, bn_info, target_mat, tgt_mapping,
                         target_renderer, is_normal, source_name, input_plug,
                         outcome, source_space):
        renderer_short = RENDERER_SHORT.get(target_renderer, target_renderer)
        bn_suffix = "_" + renderer_short + ("Nrm" if is_normal else "Bump")
        try:
            bn_node = cmds.shadingNode(tgt_mapping.node_type, asUtility=True,
                                       name=source_name + bn_suffix)
        except Exception as exc:
            outcome.ok = False
            outcome.critical.append(f"failed to create {tgt_mapping.node_type}: {exc}")
            self.log.error(f"Failed to create {tgt_mapping.node_type}: {exc}", source=_SOURCE, nodes=(target_mat,))
            return
        self.log.debug(f"Created bump/normal node {bn_node}", source=_SOURCE, nodes=(bn_node,))

        if tgt_mapping.scale and bn_info.get("scale") is not None:
            try:
                cmds.setAttr(f"{bn_node}.{tgt_mapping.scale}", bn_info["scale"])
                self.log.debug(f"Set {bn_node}.{tgt_mapping.scale} = {bn_info['scale']!r}", source=_SOURCE, nodes=(bn_node,))
            except Exception as exc:
                outcome.ok = False
                outcome.critical.append(f"failed to set scale on {bn_node}: {exc}")
                self.log.warn(f"Failed to set scale on {bn_node}: {exc}", source=_SOURCE, nodes=(bn_node,))

        if tgt_mapping.input:
            if self.utils.smart_connect(input_plug, f"{bn_node}.{tgt_mapping.input}", logger=self.log):
                self.log.debug(
                    f"Connected bump/normal source {input_plug} -> {bn_node}.{tgt_mapping.input}",
                    source=_SOURCE,
                    nodes=(self.utils.node_name_from_plug(input_plug), bn_node),
                )
            else:
                outcome.ok = False
                outcome.critical.append(f"failed to connect {input_plug} -> {bn_node}.{tgt_mapping.input}")
                self.log.warn(
                    f"Failed to connect {input_plug} -> {bn_node}.{tgt_mapping.input}",
                    source=_SOURCE,
                    nodes=(self.utils.node_name_from_plug(input_plug), bn_node),
                )

        self._apply_normal_mode(bn_node, tgt_mapping, source_space, outcome)

        try:
            target_type = cmds.nodeType(target_mat)
        except Exception as exc:
            outcome.ok = False
            outcome.critical.append(f"failed to identify target material {target_mat}: {exc}")
            self.log.warn(f"Failed to identify target material {target_mat}: {exc}", source=_SOURCE, nodes=(target_mat,))
            return
        common_config = self.config.get_material_config(target_type)
        if common_config:
            bump_attr = common_config.attr_map.get("normal_bump", "")
            if bump_attr:
                try:
                    cmds.connectAttr(f"{bn_node}.{tgt_mapping.output}",
                                     f"{target_mat}.{bump_attr}", force=True)
                    self.log.info(
                        f"Bump/Normal: connected {bn_node} -> {target_mat}.{bump_attr}",
                        source=_SOURCE,
                        nodes=(bn_node, target_mat),
                    )
                except Exception as exc:
                    outcome.ok = False
                    outcome.critical.append(f"failed to connect {bn_node} -> {target_mat}.{bump_attr}: {exc}")
                    self.log.warn(f"Failed to connect {bn_node} -> {target_mat}.{bump_attr}: {exc}", source=_SOURCE, nodes=(bn_node, target_mat))

        if outcome.ok:
            self.log.info(f"Bump/Normal: converted to {tgt_mapping.node_type} node", source=_SOURCE, nodes=(bn_node, target_mat))
        else:
            self.log.warn(f"Bump/Normal: conversion to {tgt_mapping.node_type} node incomplete", source=_SOURCE, nodes=(bn_node, target_mat))

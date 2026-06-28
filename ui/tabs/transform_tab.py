from core.builder_context import BuilderContext

try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui
import maya.cmds as cmds


class TransformTab:

    def __init__(self, ctx: BuilderContext):
        self.ctx = ctx

    def build_ui(self):
        widget = QtWidgets.QWidget()
        widget.setObjectName("transformToolsTab")

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setObjectName("toolScrollArea")

        container = QtWidgets.QWidget()
        container.setObjectName("toolContainer")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        grp_align = QtWidgets.QGroupBox("Pivot & Alignment")
        align_layout = QtWidgets.QVBoxLayout(grp_align)
        align_layout.setSpacing(8)
        align_layout.setContentsMargins(15, 20, 15, 15)

        btn_floor = QtWidgets.QPushButton("Align To Floor")
        btn_floor.setFixedHeight(40)
        btn_floor.clicked.connect(self._floor)
        align_layout.addWidget(btn_floor)

        grid_layout = QtWidgets.QGridLayout()
        grid_layout.setSpacing(6)
        axis_buttons = [
            ("X -", self._x_min), ("Y -", self._y_min), ("Z -", self._z_min),
            ("X +", self._x_max), ("Y +", self._y_max), ("Z +", self._z_max),
        ]
        positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
        for (label, handler), pos in zip(axis_buttons, positions):
            btn = QtWidgets.QPushButton(label)
            btn.setFixedHeight(32)
            btn.clicked.connect(handler)
            grid_layout.addWidget(btn, *pos)
        align_layout.addLayout(grid_layout)

        btn_center = QtWidgets.QPushButton("Center Pivots")
        btn_center.setFixedHeight(35)
        btn_center.clicked.connect(self._center_pivots)
        align_layout.addWidget(btn_center)

        layout.addWidget(grp_align)

        grp_loc = QtWidgets.QGroupBox("World Space Location")
        loc_layout = QtWidgets.QHBoxLayout(grp_loc)
        loc_layout.setSpacing(8)
        loc_layout.setContentsMargins(15, 20, 15, 15)

        fields_layout = QtWidgets.QFormLayout()
        fields_layout.setHorizontalSpacing(10)
        fields_layout.setVerticalSpacing(6)

        self.tf_x = QtWidgets.QLineEdit("0")
        self.tf_y = QtWidgets.QLineEdit("0")
        self.tf_z = QtWidgets.QLineEdit("0")

        fields_layout.addRow(" X :", self.tf_x)
        fields_layout.addRow(" Y :", self.tf_y)
        fields_layout.addRow(" Z :", self.tf_z)
        loc_layout.addLayout(fields_layout)

        btn_set = QtWidgets.QPushButton("Set")
        btn_set.setObjectName("setLocBtn")
        btn_set.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        btn_set.setMinimumWidth(55)
        btn_set.clicked.connect(self._w_move)
        loc_layout.addWidget(btn_set)

        layout.addWidget(grp_loc)

        grp_freeze = QtWidgets.QGroupBox("Freeze Transformations")
        freeze_layout = QtWidgets.QVBoxLayout(grp_freeze)
        freeze_layout.setSpacing(8)
        freeze_layout.setContentsMargins(15, 20, 15, 15)

        freeze_buttons = [
            ("Freeze Translation", self._freeze_translation),
            ("Freeze Rotation", self._freeze_rotation),
            ("Freeze Scale", self._freeze_scale),
            ("Freeze All", self._freeze_all),
        ]
        for label, handler in freeze_buttons:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedHeight(35)
            btn.clicked.connect(handler)
            freeze_layout.addWidget(btn)

        layout.addWidget(grp_freeze)

        btn_apply_all = QtWidgets.QPushButton("Apply All (Execute Pipeline)")
        btn_apply_all.setObjectName("applyTransformBtn")
        btn_apply_all.setFixedHeight(42)
        btn_apply_all.clicked.connect(self._run_transform_pipeline)
        layout.addWidget(btn_apply_all)

        layout.addStretch()

        scroll.setWidget(container)
        tab_layout = QtWidgets.QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def _w_move(self):
        obj_sel = cmds.ls(sl=1)
        try:
            px = float(self.tf_x.text())
            py = float(self.tf_y.text())
            pz = float(self.tf_z.text())
            for obj in obj_sel:
                cmds.move(px, py, pz, obj, rpr=1)
        except ValueError:
            cmds.warning("Please enter valid numeric coordinates.")

    def _freeze_translation(self):
        for obj in cmds.ls(sl=1):
            cmds.makeIdentity(obj, apply=True, translate=True)

    def _freeze_rotation(self):
        for obj in cmds.ls(sl=1):
            cmds.makeIdentity(obj, apply=True, rotate=True)

    def _freeze_scale(self):
        for obj in cmds.ls(sl=1):
            cmds.makeIdentity(obj, apply=True, scale=True)

    def _freeze_all(self):
        for obj in cmds.ls(sl=1):
            cmds.makeIdentity(obj, apply=True, translate=True, rotate=True, scale=True)

    def _center_pivots(self):
        for obj in cmds.ls(sl=1):
            cmds.xform(obj, cp=1)

    def _floor(self):
        obj_sel = cmds.ls(sl=1)
        if not obj_sel:
            return
        s_vtx = cmds.polyListComponentConversion(obj_sel, tv=1)
        cmds.select(s_vtx)
        vertex_list = cmds.ls(sl=1, fl=1)
        if not vertex_list:
            cmds.select(obj_sel)
            return
        y_positions = [cmds.xform(v, q=1, t=1, ws=1)[1] for v in vertex_list]
        cmds.xform(obj_sel, ws=1, r=1, t=(0, -min(y_positions), 0))
        cmds.select(obj_sel)

    def _axis_op(self, axis_index, mode):
        obj_sel = cmds.ls(sl=1)
        for obj in obj_sel:
            s_vtx = cmds.polyListComponentConversion(obj, tv=1)
            cmds.select(s_vtx)
            vertex_list = cmds.ls(sl=1, fl=1)
            if not vertex_list:
                continue
            positions = [cmds.xform(v, q=1, t=1, ws=1)[axis_index] for v in vertex_list]
            bound = min(positions) if mode == 'min' else max(positions)
            rp = cmds.xform(obj, q=1, rp=1, ws=1)
            length = -rp[axis_index] + bound
            offset = [0, 0, 0]
            offset[axis_index] = length
            cmds.xform(obj, ws=1, r=1, rp=(offset[0], offset[1], offset[2]))
            cmds.xform(obj, ws=1, a=1, sp=cmds.xform(obj, q=1, rp=1, ws=1))
        cmds.select(obj_sel)

    def _x_min(self): self._axis_op(0, 'min')
    def _x_max(self): self._axis_op(0, 'max')
    def _y_min(self): self._axis_op(1, 'min')
    def _y_max(self): self._axis_op(1, 'max')
    def _z_min(self): self._axis_op(2, 'min')
    def _z_max(self): self._axis_op(2, 'max')

    def _run_transform_pipeline(self):
        self._center_pivots()
        self._w_move()
        self._floor()
        self._y_min()
        self._freeze_all()

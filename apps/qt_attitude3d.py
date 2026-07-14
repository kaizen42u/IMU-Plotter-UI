"""3-D attitude visualization pane — submarine hull over a ground plane (OpenGL)."""

import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QMatrix4x4
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

_HULL_RADIUS = 1.0
_HULL_LENGTH = 4.5
_AXIS_LEN    = 2.2
_GROUND_Z    = -1.8


def _hull_meshdata() -> gl.MeshData:
    """Cylinder along +X, centered at the origin (baked into vertices)."""
    md = gl.MeshData.cylinder(rows=2, cols=32,
                              radius=[_HULL_RADIUS, _HULL_RADIUS],
                              length=_HULL_LENGTH)
    verts = md.vertexes()
    # cylinder() builds along +Z from 0..length → center it, then Z→X:
    # (x, y, z) → (z - L/2, y, -x) is a proper rotation about Y.
    v = np.empty_like(verts)
    v[:, 0] = verts[:, 2] - _HULL_LENGTH / 2
    v[:, 1] = verts[:, 1]
    v[:, 2] = -verts[:, 0]
    return gl.MeshData(vertexes=v, faces=md.faces())


def _cap_meshdata(x: float, cols: int = 32) -> gl.MeshData:
    """Disk (triangle fan) in the Y-Z plane at the given X."""
    ang = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    rim = np.column_stack([
        np.full(cols, x),
        _HULL_RADIUS * np.cos(ang),
        _HULL_RADIUS * np.sin(ang),
    ])
    verts = np.vstack([[x, 0.0, 0.0], rim])
    faces = np.array([[0, 1 + i, 1 + (i + 1) % cols] for i in range(cols)])
    return gl.MeshData(vertexes=verts, faces=faces)


class Attitude3DWindow(QWidget):
    """Standalone 3-D attitude view. Feed it with set_attitude()."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("3D Attitude")
        self.setWindowFlag(Qt.WindowType.Window)

        self._yaw = 0.0
        self._pitch = 0.0
        self._roll = 0.0
        self._src = ""
        self._dirty = True

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Header: source + angles ───────────────────────────────────
        hdr = QHBoxLayout()
        self._hdr_lbl = QLabel("Y: 0.0°   P: 0.0°   R: 0.0°")
        self._hdr_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        hdr.addWidget(self._hdr_lbl)
        hdr.addStretch()
        hint = QLabel("drag: orbit   wheel: zoom")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hdr.addWidget(hint)
        root.addLayout(hdr)

        # ── GL scene ──────────────────────────────────────────────────
        self._view = gl.GLViewWidget()
        self._view.setBackgroundColor("#16181d")
        self._view.setCameraPosition(distance=11, elevation=22, azimuth=-55)
        self._view.setMinimumSize(380, 380)
        root.addWidget(self._view, 1)  # all extra space goes to the GL view

        self._build_scene()

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._redraw_if_dirty)
        self._timer.start()

        self.adjustSize()

    # ------------------------------------------------------------------
    def _build_scene(self) -> None:
        v = self._view

        # Ground plane — earth reference, never moves
        grid = gl.GLGridItem()
        grid.setSize(12, 12)
        grid.setSpacing(0.5, 0.5)
        grid.translate(0, 0, _GROUND_Z)
        v.addItem(grid)

        # North / East reference arrows on the ground
        z = _GROUND_Z + 0.01
        north = gl.GLLinePlotItem(
            pos=np.array([[0, 0, z], [5.0, 0, z]]),
            color=(0.9, 0.3, 0.3, 0.9), width=2, antialias=True)
        east = gl.GLLinePlotItem(
            pos=np.array([[0, 0, z], [0, 5.0, z]]),
            color=(0.5, 0.7, 0.5, 0.7), width=2, antialias=True)
        v.addItem(north)
        v.addItem(east)
        n_lbl = gl.GLTextItem(pos=(5.3, 0, z), text="N", color=(230, 80, 80))
        e_lbl = gl.GLTextItem(pos=(0, 5.3, z), text="E", color=(130, 180, 130))
        v.addItem(n_lbl)
        v.addItem(e_lbl)

        # Vehicle — hull + caps + body axes, all driven by one transform
        self._vehicle_items: list = []

        hull = gl.GLMeshItem(
            meshdata=_hull_meshdata(),
            smooth=True, shader="shaded",
            color=(0.35, 0.5, 0.7, 1.0),
            drawEdges=False,
        )
        v.addItem(hull)
        self._vehicle_items.append(hull)

        nose = gl.GLMeshItem(
            meshdata=_cap_meshdata(_HULL_LENGTH / 2),
            smooth=False, shader="shaded",
            color=(0.85, 0.2, 0.2, 1.0),
        )
        tail = gl.GLMeshItem(
            meshdata=_cap_meshdata(-_HULL_LENGTH / 2),
            smooth=False, shader="shaded",
            color=(0.45, 0.5, 0.55, 1.0),
        )
        v.addItem(nose)
        v.addItem(tail)
        self._vehicle_items += [nose, tail]

        for vec, color in [
            ((_AXIS_LEN, 0, 0), (1.0, 0.25, 0.25, 1.0)),   # X fwd  red
            ((0, _AXIS_LEN, 0), (0.25, 0.8, 0.25, 1.0)),   # Y      green
            ((0, 0, _AXIS_LEN), (0.3, 0.55, 1.0, 1.0)),    # Z up   blue
        ]:
            line = gl.GLLinePlotItem(
                pos=np.array([[0.0, 0.0, 0.0], list(vec)]),
                color=color, width=3, antialias=True)
            v.addItem(line)
            self._vehicle_items.append(line)

    # ------------------------------------------------------------------
    def set_attitude(self, yaw: float, pitch: float, roll: float, src: str = "") -> None:
        if (yaw, pitch, roll, src) == (self._yaw, self._pitch, self._roll, self._src):
            return
        self._yaw, self._pitch, self._roll = yaw, pitch, roll
        self._src = src
        self._dirty = True

    def _redraw_if_dirty(self) -> None:
        if not self._dirty or not self.isVisible():
            return
        self._dirty = False

        m = QMatrix4x4()
        m.rotate(self._yaw,   0, 0, 1)   # heading  about earth Z
        m.rotate(self._pitch, 0, 1, 0)   # pitch    about body Y
        m.rotate(self._roll,  1, 0, 0)   # roll     about body X
        for item in self._vehicle_items:
            item.setTransform(m)

        prefix = f"[{self._src}]   " if self._src else ""
        self._hdr_lbl.setText(
            f"{prefix}Y: {self._yaw:.1f}°   P: {self._pitch:.1f}°   R: {self._roll:.1f}°"
        )

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:
        self._dirty = True
        if not self._timer.isActive():
            self._timer.start()
        super().showEvent(event)

    def closeEvent(self, event) -> None:
        # Window is only hidden on close (may be re-shown) — pause the timer.
        self._timer.stop()
        super().closeEvent(event)

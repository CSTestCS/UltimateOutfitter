"""Upscaler for low-resolution / pixelated textures."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QPainter
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ..core import imaging, upscale
from ..core.storage import unique_path
from .common import IMAGE_FILTER, AppState, array_to_pixmap, checker_pixmap, run_with_progress


class ZoomView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(checker_pixmap()))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.item = None

    def set_array(self, arr, fit=True):
        self.scene().clear()
        self.item = self.scene().addPixmap(array_to_pixmap(arr))
        self.scene().setSceneRect(self.item.boundingRect())
        if fit:
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(f, f)


class UpscaleTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.path: Path | None = None
        self.src: np.ndarray | None = None
        self.result: np.ndarray | None = None

        self.method = QComboBox()
        for key, label in upscale.METHODS.items():
            self.method.addItem(label, key)
        self.scale = QDoubleSpinBox()
        self.scale.setRange(1.0, 16.0)
        self.scale.setSingleStep(1.0)
        self.scale.setValue(4.0)
        self.smooth = QDoubleSpinBox()
        self.smooth.setRange(0.0, 4.0)
        self.smooth.setSingleStep(0.1)
        self.smooth.setValue(1.0)
        self.smooth.setToolTip("How strongly shapes are rounded (in source pixels)")
        self.blend = QDoubleSpinBox()
        self.blend.setRange(0.1, 4.0)
        self.blend.setSingleStep(0.1)
        self.blend.setValue(0.8)
        self.blend.setToolTip("Width of the in-between colour gradients (in source pixels)")
        self.colors = QSpinBox()
        self.colors.setRange(2, 256)
        self.colors.setValue(64)
        self.colors.setToolTip("Images with more colours are quantised to this many for shape smoothing")
        b_open = QPushButton("Open image…")
        b_open.clicked.connect(self.open_dialog)
        b_run = QPushButton("Upscale")
        b_run.setStyleSheet("font-weight:bold;")
        b_run.clicked.connect(self.run)
        b_save = QPushButton("Save as new…")
        b_save.clicked.connect(self.save_as)
        b_over = QPushButton("Overwrite original")
        b_over.clicked.connect(self.overwrite)
        b_edit = QPushButton("Send result to editor")
        b_edit.clicked.connect(self.to_editor)
        self.method.currentIndexChanged.connect(self._toggle)

        form = QFormLayout()
        form.addRow("Method", self.method)
        form.addRow("Scale ×", self.scale)
        form.addRow("Shape smoothing", self.smooth)
        form.addRow("Blend width", self.blend)
        form.addRow("Max colours", self.colors)
        controls = QVBoxLayout()
        controls.addWidget(b_open)
        controls.addLayout(form)
        controls.addWidget(b_run)
        controls.addWidget(b_save)
        controls.addWidget(b_over)
        controls.addWidget(b_edit)
        help_text = QLabel(
            "<b>Smooth shapes – no antialiasing</b>: rounds the stair-stepped outlines of every colour "
            "area but keeps hard edges and the original colours.<br><br>"
            "<b>Smooth shapes – antialiased</b>: the same smoothing with soft, antialiased edges.<br><br>"
            "<b>In-between colours</b>: smooth shapes plus a short gradient at every colour change.<br><br>"
            "Scroll to zoom, drag to pan.")
        help_text.setWordWrap(True)
        controls.addWidget(help_text)
        controls.addStretch(1)
        cw = QWidget()
        cw.setLayout(controls)
        cw.setMaximumWidth(320)

        self.before = ZoomView()
        self.after = ZoomView()
        self.info = QLabel("Open a low-resolution texture to upscale.")
        views = QHBoxLayout()
        bv = QVBoxLayout()
        bv.addWidget(QLabel("Original (nearest-neighbour zoom)"))
        bv.addWidget(self.before)
        av = QVBoxLayout()
        av.addWidget(QLabel("Result"))
        av.addWidget(self.after)
        views.addLayout(bv)
        views.addLayout(av)
        right = QVBoxLayout()
        right.addLayout(views, 1)
        right.addWidget(self.info)
        lay = QHBoxLayout(self)
        lay.addWidget(cw)
        lay.addLayout(right, 1)
        state.open_in_upscaler.connect(self.open_path)
        self._toggle()

    def _toggle(self, *_):
        m = self.method.currentData()
        self.smooth.setEnabled(m in ("shape", "shape_aa", "blend"))
        self.colors.setEnabled(m in ("shape", "shape_aa", "blend"))
        self.blend.setEnabled(m == "blend")

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open image", "", IMAGE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        try:
            self.src = imaging.load_rgba(path)
        except OSError as exc:
            QMessageBox.critical(self, "Open", str(exc))
            return
        self.path = Path(path)
        self.result = None
        h, w = self.src.shape[:2]
        self.before.set_array(self.src)
        self.after.scene().clear()
        self.info.setText(f"{self.path.name}: {w}×{h}px")

    def run(self):
        if self.src is None:
            return
        method = self.method.currentData()
        scale = self.scale.value()
        h, w = self.src.shape[:2]
        if w * h * scale * scale > 64_000_000:
            QMessageBox.warning(self, "Upscale", "The result would be too large (over 64 megapixels).")
            return

        def work(progress=None):
            return upscale.upscale(self.src, method, scale, self.smooth.value(), self.blend.value(),
                                   self.colors.value(),
                                   progress=(lambda f: progress(int(f * 100), 100, "")) if progress else None)

        def done(result):
            self.result = result
            self.after.set_array(result)
            # show the original at the same zoom for comparison
            self.before.resetTransform()
            self.before.fitInView(self.before.item, Qt.AspectRatioMode.KeepAspectRatio)
            rh, rw = result.shape[:2]
            self.info.setText(f"{self.path.name}: {w}×{h}px → {rw}×{rh}px "
                              f"({self.method.currentText()})")
        run_with_progress(self, "Upscaling", work, on_done=done, pass_progress=True)

    def save_as(self):
        if self.result is None:
            return
        default = unique_path(self.state.library.root / "Upscaled" /
                              f"{self.path.stem}-x{self.scale.value():g}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save upscaled image", str(default), "PNG (*.png)")
        if path:
            imaging.save_rgba(self.result, path)
            self.info.setText(f"Saved {path}")

    def overwrite(self):
        if self.result is None or self.path is None:
            return
        if QMessageBox.question(self, "Overwrite", f"Overwrite the original file?\n{self.path}") == \
                QMessageBox.StandardButton.Yes:
            imaging.save_rgba(self.result, self.path)
            self.state.library_changed.emit()
            self.info.setText(f"Overwrote {self.path}")

    def to_editor(self):
        if self.result is None:
            return
        path = unique_path(self.state.library.root / "Upscaled" / f"{self.path.stem}-x{self.scale.value():g}.png")
        imaging.save_rgba(self.result, path)
        self.state.open_in_editor.emit(str(path))

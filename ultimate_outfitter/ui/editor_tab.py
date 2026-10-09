"""Image editor: colour / hue / connected selections, palette recolouring and patterns."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from ..core import imaging
from ..core.storage import unique_path
from .common import IMAGE_FILTER, AppState, SwatchRow, array_to_pixmap, busy, checker_pixmap, palette_pixmap

TOOLS = [
    ("wand", "Magic wand (connected colour)"),
    ("color", "Select colour (whole image)"),
    ("hue", "Select hue (whole image)"),
    ("hue_wand", "Select hue (connected)"),
    ("rect", "Rectangle"),
    ("brush", "Brush"),
    ("pan", "Pan / zoom"),
]


class Canvas(QGraphicsView):
    clicked = Signal(int, int, object)        # x, y, modifiers
    rect_selected = Signal(int, int, int, int, object)
    brushed = Signal(int, int, bool)          # x, y, erase (right button)
    brush_released = Signal()

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(checker_pixmap()))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.pix_item = QGraphicsPixmapItem()
        self.overlay_item = QGraphicsPixmapItem()
        self.scene().addItem(self.pix_item)
        self.scene().addItem(self.overlay_item)
        self.rubber = QGraphicsRectItem()
        self.rubber.setPen(QPen(QColor("#00e5ff"), 0, Qt.PenStyle.DashLine))
        self.rubber.setVisible(False)
        self.scene().addItem(self.rubber)
        self.tool = "wand"
        self._drag_start: QPointF | None = None
        self.brush_size = 10

    def set_images(self, pixmap: QPixmap, overlay: QPixmap | None):
        self.pix_item.setPixmap(pixmap)
        self.overlay_item.setPixmap(overlay if overlay else QPixmap())
        self.scene().setSceneRect(QRectF(pixmap.rect()))

    def fit(self):
        self.fitInView(self.pix_item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

    def _img_pos(self, e):
        p = self.mapToScene(e.position().toPoint())
        return int(np.floor(p.x())), int(np.floor(p.y())), p

    def mousePressEvent(self, e):
        if self.tool == "pan" or e.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            super().mousePressEvent(e)
            return
        x, y, p = self._img_pos(e)
        if self.tool == "rect":
            self._drag_start = p
            self.rubber.setRect(QRectF(p, p))
            self.rubber.setVisible(True)
        elif self.tool == "brush":
            self.brushed.emit(x, y, e.button() == Qt.MouseButton.RightButton)
        else:
            self.clicked.emit(x, y, e.modifiers())

    def mouseMoveEvent(self, e):
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            super().mouseMoveEvent(e)
            return
        x, y, p = self._img_pos(e)
        if self.tool == "rect" and self._drag_start is not None:
            self.rubber.setRect(QRectF(self._drag_start, p).normalized())
        elif self.tool == "brush" and e.buttons():
            self.brushed.emit(x, y, bool(e.buttons() & Qt.MouseButton.RightButton))

    def mouseReleaseEvent(self, e):
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            super().mouseReleaseEvent(e)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        if self.tool == "rect" and self._drag_start is not None:
            r = self.rubber.rect()
            self.rubber.setVisible(False)
            self._drag_start = None
            self.rect_selected.emit(int(r.left()), int(r.top()), int(np.ceil(r.right())),
                                    int(np.ceil(r.bottom())), e.modifiers())
        elif self.tool == "brush":
            self.brush_released.emit()


class EditorTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.path: Path | None = None
        self.original: np.ndarray | None = None   # as loaded (used by "erase texture")
        self.image: np.ndarray | None = None
        self.selection: np.ndarray | None = None
        self.undo_stack: list[tuple[np.ndarray, np.ndarray]] = []
        self.redo_stack: list[tuple[np.ndarray, np.ndarray]] = []
        self.dirty = False

        self.canvas = Canvas()
        self.canvas.clicked.connect(self._on_click)
        self.canvas.rect_selected.connect(self._on_rect)
        self.canvas.brushed.connect(self._on_brush)
        self.canvas.brush_released.connect(self._end_brush)
        self.status = QLabel("Open an image to start editing.")

        # ---- file
        b_open = QPushButton("Open…")
        b_save = QPushButton("Save (overwrite)")
        b_save_as = QPushButton("Save as new…")
        b_undo = QPushButton("Undo")
        b_redo = QPushButton("Redo")
        b_revert = QPushButton("Revert all")
        b_fit = QPushButton("Fit")
        b_open.clicked.connect(self.open_dialog)
        b_save.clicked.connect(self.save_overwrite)
        b_save_as.clicked.connect(self.save_as)
        b_undo.clicked.connect(self.undo)
        b_redo.clicked.connect(self.redo)
        b_revert.clicked.connect(self.revert)
        b_fit.clicked.connect(self.canvas.fit)
        filebar = QHBoxLayout()
        for b in (b_open, b_save, b_save_as, b_undo, b_redo, b_revert, b_fit):
            filebar.addWidget(b)
        filebar.addStretch(1)

        # ---- selection tools
        sel_box = QGroupBox("Selection")
        sl = QVBoxLayout(sel_box)
        self.tool_group = QButtonGroup(self)
        for i, (tid, label) in enumerate(TOOLS):
            rb = QRadioButton(label)
            rb.setProperty("tool", tid)
            self.tool_group.addButton(rb, i)
            sl.addWidget(rb)
            if i == 0:
                rb.setChecked(True)
        self.tool_group.buttonClicked.connect(lambda b: setattr(self.canvas, "tool", b.property("tool")))
        self.mode = QComboBox()
        self.mode.addItems(["Replace", "Add (Shift)", "Subtract (Alt)", "Intersect"])
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 100)
        self.tolerance.setValue(15)
        self.tolerance.setToolTip("Colour tolerance (ΔE) for colour tools")
        self.hue_tol = QSpinBox()
        self.hue_tol.setRange(1, 180)
        self.hue_tol.setValue(15)
        self.brush = QSpinBox()
        self.brush.setRange(1, 300)
        self.brush.setValue(10)
        self.brush.valueChanged.connect(lambda v: setattr(self.canvas, "brush_size", v))
        self.show_overlay = QCheckBox("Show selection overlay")
        self.show_overlay.setChecked(True)
        self.show_overlay.toggled.connect(self._refresh)
        f = QFormLayout()
        f.addRow("Mode", self.mode)
        f.addRow("Colour tolerance", self.tolerance)
        f.addRow("Hue tolerance (°)", self.hue_tol)
        f.addRow("Brush size (right-drag erases)", self.brush)
        sl.addLayout(f)
        sl.addWidget(self.show_overlay)
        row = QHBoxLayout()
        for label, fn in (("All", self.select_all), ("None", self.select_none), ("Invert", self.invert),
                          ("Subject", self.select_subject)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        sl.addLayout(row)
        row2 = QHBoxLayout()
        for label, fn in (("Grow", lambda: self.grow(1)), ("Shrink", lambda: self.grow(-1))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row2.addWidget(b)
        sl.addLayout(row2)

        # ---- recolour
        rec_box = QGroupBox("Recolour selection")
        rl = QVBoxLayout(rec_box)
        self.palette_combo = QComboBox()
        self.palette_combo.setIconSize(palette_pixmap(["#000"], 120, 16).size())
        self.palette_combo.currentIndexChanged.connect(self._palette_changed)
        self.palette2_combo = QComboBox()
        self.palette2_combo.setIconSize(palette_pixmap(["#000"], 120, 16).size())
        self.swatches = SwatchRow()
        self.swatches.clicked.connect(self.tint_color)
        self.recolor_mode = QComboBox()
        self.recolor_mode.addItem("Region match (keeps shading, multi-colour)", "regions")
        self.recolor_mode.addItem("Gradient map by lightness", "gradient")
        self.strength = QSlider(Qt.Orientation.Horizontal)
        self.strength.setRange(10, 100)
        self.strength.setValue(100)
        b_recolor = QPushButton("Apply palette to selection")
        b_recolor.clicked.connect(self.recolor)
        rl.addWidget(QLabel("Palette"))
        rl.addWidget(self.palette_combo)
        rl.addWidget(QLabel("Optional 2nd palette (region mode)"))
        rl.addWidget(self.palette2_combo)
        rl.addWidget(QLabel("Click a swatch to tint the selection with that single colour:"))
        rl.addWidget(self.swatches)
        rl.addWidget(self.recolor_mode)
        sf = QFormLayout()
        sf.addRow("Strength", self.strength)
        rl.addLayout(sf)
        rl.addWidget(b_recolor)

        # ---- pattern
        pat_box = QGroupBox("Pattern (masked to the selection)")
        pl = QFormLayout(pat_box)
        self.pattern_combo = QComboBox()
        self.pattern_combo.setIconSize(palette_pixmap(["#000"], 32, 32).size())
        self.pat_palette = QComboBox()
        self.pat_palette.setIconSize(palette_pixmap(["#000"], 120, 16).size())
        self.pat_scale = QDoubleSpinBox()
        self.pat_scale.setRange(0.05, 20)
        self.pat_scale.setSingleStep(0.25)
        self.pat_scale.setValue(1.0)
        self.pat_aa = QCheckBox("Antialias when scaling")
        self.pat_aa.setChecked(True)
        self.pat_tiled = QCheckBox("Tile")
        self.pat_tiled.setChecked(True)
        self.pat_ox = QSpinBox()
        self.pat_ox.setRange(-5000, 5000)
        self.pat_oy = QSpinBox()
        self.pat_oy.setRange(-5000, 5000)
        self.pat_blend = QComboBox()
        self.pat_blend.addItem("Keep shading", "shaded")
        self.pat_blend.addItem("Replace", "replace")
        self.pat_blend.addItem("Multiply", "multiply")
        self.pat_opacity = QSlider(Qt.Orientation.Horizontal)
        self.pat_opacity.setRange(5, 100)
        self.pat_opacity.setValue(100)
        b_pat = QPushButton("Apply pattern")
        b_pat.clicked.connect(self.apply_pattern)
        b_erase = QPushButton("Erase texture / changes in selection")
        b_erase.setToolTip("Restore the original pixels inside the selection")
        b_erase.clicked.connect(self.erase_texture)
        offs = QHBoxLayout()
        offs.addWidget(self.pat_ox)
        offs.addWidget(self.pat_oy)
        pl.addRow("Pattern", self.pattern_combo)
        pl.addRow("Palette", self.pat_palette)
        pl.addRow("Scale", self.pat_scale)
        pl.addRow(self.pat_aa, self.pat_tiled)
        pl.addRow("Offset x / y", offs)
        pl.addRow("Blend", self.pat_blend)
        pl.addRow("Opacity", self.pat_opacity)
        pl.addRow(b_pat)
        pl.addRow(b_erase)

        side = QWidget()
        sv = QVBoxLayout(side)
        sv.addWidget(sel_box)
        sv.addWidget(rec_box)
        sv.addWidget(pat_box)
        sv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(380)
        scroll.setMaximumWidth(440)

        main = QVBoxLayout(self)
        main.addLayout(filebar)
        body = QHBoxLayout()
        body.addWidget(self.canvas, 1)
        body.addWidget(scroll)
        main.addLayout(body, 1)
        main.addWidget(self.status)

        state.library_changed.connect(self.refresh_library)
        state.open_in_editor.connect(self.open_path)
        self.refresh_library()

    # ------------------------------------------------------------------ library
    def refresh_library(self):
        lib = self.state.library
        for combo, allow_none in ((self.palette_combo, False), (self.palette2_combo, True),
                                  (self.pat_palette, True)):
            cur = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            if allow_none:
                combo.addItem("(none)", None)
            for pal in sorted(lib.palettes.values(), key=lambda p: p["name"].lower()):
                combo.addItem(QIcon(palette_pixmap(pal["colors"], 120, 16)), pal["name"], pal["id"])
            idx = combo.findData(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        cur = self.pattern_combo.currentData()
        self.pattern_combo.clear()
        from .common import thumb_cache
        for pat in sorted(lib.patterns.values(), key=lambda p: p["name"].lower()):
            self.pattern_combo.addItem(QIcon(thumb_cache.get(lib.abspath(pat["image"]), 32)), pat["name"], pat["id"])
        idx = self.pattern_combo.findData(cur)
        if idx >= 0:
            self.pattern_combo.setCurrentIndex(idx)
        self._palette_changed()

    def _palette(self, combo) -> list[str] | None:
        pid = combo.currentData()
        pal = self.state.library.palettes.get(pid) if pid else None
        return pal["colors"] if pal else None

    def _palette_changed(self, *_):
        self.swatches.set_colors(self._palette(self.palette_combo) or [])

    # --------------------------------------------------------------------- file
    def open_dialog(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open image", str(self.state.library.root), IMAGE_FILTER)
        if path:
            self.open_path(path, ask=False)

    def _confirm_discard(self) -> bool:
        if self.dirty:
            r = QMessageBox.question(self, "Unsaved changes", "Discard unsaved changes?")
            return r == QMessageBox.StandardButton.Yes
        return True

    def open_path(self, path: str, ask: bool = True):
        if ask and not self._confirm_discard():
            return
        try:
            img = imaging.load_rgba(path)
        except OSError as exc:
            QMessageBox.critical(self, "Open", str(exc))
            return
        self.path = Path(path)
        self.original = img.copy()
        self.image = img
        self.selection = np.zeros(img.shape[:2], dtype=bool)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False
        self._refresh()
        self.canvas.resetTransform()
        self.canvas.fit()

    def save_overwrite(self):
        if self.image is None or self.path is None:
            return
        r = QMessageBox.question(self, "Overwrite", f"Overwrite the original file?\n{self.path}")
        if r == QMessageBox.StandardButton.Yes:
            imaging.save_rgba(self.image, self.path)
            self.original = self.image.copy()
            self.dirty = False
            from .common import thumb_cache
            thumb_cache.clear()
            self.state.library_changed.emit()
            self.status.setText(f"Saved {self.path}")

    def save_as(self):
        if self.image is None:
            return
        default = unique_path((self.path.parent if self.path else self.state.library.root / "Edited")
                              / f"{self.path.stem if self.path else 'image'}-edited.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save as new image", str(default),
                                              "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)")
        if path:
            imaging.save_rgba(self.image, path)
            self.path = Path(path)
            self.dirty = False
            self.status.setText(f"Saved new image {path}")

    # ------------------------------------------------------------------ history
    def _push(self):
        self.undo_stack.append((self.image.copy(), self.selection.copy()))
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append((self.image, self.selection))
            self.image, self.selection = self.undo_stack.pop()
            self._refresh()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append((self.image, self.selection))
            self.image, self.selection = self.redo_stack.pop()
            self._refresh()

    def revert(self):
        if self.original is not None:
            self._push()
            self.image = self.original.copy()
            self._refresh()

    # ------------------------------------------------------------------ drawing
    def _refresh(self, *_):
        if self.image is None:
            return
        overlay = None
        if self.show_overlay.isChecked() and self.selection is not None and self.selection.any():
            ov = np.zeros(self.image.shape, dtype=np.uint8)
            ov[self.selection] = (0, 200, 255, 90)
            # outline
            edge = self.selection ^ (np.pad(self.selection, 1)[2:, 1:-1] & np.pad(self.selection, 1)[:-2, 1:-1]
                                     & np.pad(self.selection, 1)[1:-1, 2:] & np.pad(self.selection, 1)[1:-1, :-2])
            ov[edge & self.selection] = (0, 120, 255, 255)
            overlay = array_to_pixmap(ov)
        self.canvas.set_images(array_to_pixmap(self.image), overlay)
        n = int(self.selection.sum()) if self.selection is not None else 0
        h, w = self.image.shape[:2]
        self.status.setText(f"{self.path.name if self.path else ''}  {w}×{h}px   selected: {n} px"
                            + ("   (unsaved changes)" if self.dirty else ""))

    # ---------------------------------------------------------------- selecting
    def _combine(self, new: np.ndarray, modifiers=None):
        mode = self.mode.currentIndex()
        if modifiers is not None:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                mode = 1
            elif modifiers & Qt.KeyboardModifier.AltModifier:
                mode = 2
        self._push()
        if mode == 0:
            self.selection = new
        elif mode == 1:
            self.selection = self.selection | new
        elif mode == 2:
            self.selection = self.selection & ~new
        else:
            self.selection = self.selection & new
        self._refresh()

    def _inside(self, x, y) -> bool:
        return self.image is not None and 0 <= x < self.image.shape[1] and 0 <= y < self.image.shape[0]

    @busy
    def _on_click(self, x, y, mods):
        if not self._inside(x, y):
            return
        tool = self.canvas.tool
        if tool == "wand":
            new = imaging.select_color(self.image, (x, y), self.tolerance.value(), contiguous=True)
        elif tool == "color":
            new = imaging.select_color(self.image, (x, y), self.tolerance.value(), contiguous=False)
        elif tool == "hue":
            new = imaging.select_hue(self.image, (x, y), self.hue_tol.value())
        elif tool == "hue_wand":
            new = imaging.select_hue(self.image, (x, y), self.hue_tol.value(), contiguous=True)
        else:
            return
        self._combine(new, mods)

    def _on_rect(self, x0, y0, x1, y1, mods):
        if self.image is None:
            return
        h, w = self.image.shape[:2]
        new = np.zeros((h, w), dtype=bool)
        new[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
        self._combine(new, mods)

    def _on_brush(self, x, y, erase):
        if self.image is None:
            return
        if not getattr(self, "_brushing", False):
            self._push()
            self._brushing = True
        h, w = self.image.shape[:2]
        r = self.brush.value() / 2
        y0, y1 = int(max(0, y - r)), int(min(h, y + r + 1))
        x0, x1 = int(max(0, x - r)), int(min(w, x + r + 1))
        if y1 <= y0 or x1 <= x0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        disk = (yy - y) ** 2 + (xx - x) ** 2 <= r * r
        if erase:
            self.selection[y0:y1, x0:x1] &= ~disk
        else:
            self.selection[y0:y1, x0:x1] |= disk
        self._refresh()

    def _end_brush(self):
        self._brushing = False
        self._refresh()

    def select_all(self):
        if self.image is not None:
            self._push()
            self.selection = np.ones(self.image.shape[:2], dtype=bool)
            self._refresh()

    def select_none(self):
        if self.image is not None:
            self._push()
            self.selection = np.zeros(self.image.shape[:2], dtype=bool)
            self._refresh()

    def invert(self):
        if self.image is not None:
            self._push()
            self.selection = ~self.selection
            self._refresh()

    @busy
    def select_subject(self, *_):
        if self.image is not None:
            self._combine(imaging.foreground_mask(self.image))

    def grow(self, n: int):
        if self.image is None:
            return
        self._push()
        s = self.selection
        p = np.pad(s, 1)
        neigh = p[2:, 1:-1] | p[:-2, 1:-1] | p[1:-1, 2:] | p[1:-1, :-2]
        both = p[2:, 1:-1] & p[:-2, 1:-1] & p[1:-1, 2:] & p[1:-1, :-2]
        self.selection = (s | neigh) if n > 0 else (s & both)
        self._refresh()

    # ------------------------------------------------------------------ editing
    def _require_selection(self) -> bool:
        if self.image is None:
            return False
        if not self.selection.any():
            QMessageBox.information(self, "Editor", "Make a selection first (or press 'All').")
            return False
        return True

    def _commit(self, new_image: np.ndarray):
        self._push()
        self.image = new_image
        self.dirty = True
        self._refresh()

    @busy
    def recolor(self, *_):
        if not self._require_selection():
            return
        pal = self._palette(self.palette_combo)
        if not pal:
            QMessageBox.information(self, "Editor", "Create a palette in the Library first.")
            return
        strength = self.strength.value() / 100
        if self.recolor_mode.currentData() == "gradient":
            out = imaging.gradient_map(self.image, self.selection, pal)
            if strength < 1:
                out = (self.image * (1 - strength) + out * strength).round().astype(np.uint8)
        else:
            pals = [pal]
            p2 = self._palette(self.palette2_combo)
            if p2:
                pals.append(p2)
            out = imaging.recolor_regions(self.image, self.selection, pals, strength=strength)
        self._commit(out)

    @busy
    def tint_color(self, color: str):
        if self._require_selection():
            out = imaging.tint(self.image, self.selection, color)
            s = self.strength.value() / 100
            if s < 1:
                out = (self.image * (1 - s) + out * s).round().astype(np.uint8)
            self._commit(out)

    @busy
    def apply_pattern(self, *_):
        if not self._require_selection():
            return
        pid = self.pattern_combo.currentData()
        pat = self.state.library.patterns.get(pid) if pid else None
        if not pat:
            QMessageBox.information(self, "Editor", "Upload a pattern in the Library first.")
            return
        pattern = imaging.load_rgba(self.state.library.abspath(pat["image"]))
        out = imaging.apply_pattern(
            self.image, self.selection, pattern, scale=self.pat_scale.value(),
            antialias=self.pat_aa.isChecked(), tiled=self.pat_tiled.isChecked(),
            offset=(self.pat_ox.value(), self.pat_oy.value()), palette=self._palette(self.pat_palette),
            blend=self.pat_blend.currentData(), opacity=self.pat_opacity.value() / 100)
        self._commit(out)

    def erase_texture(self):
        if not self._require_selection() or self.original is None:
            return
        out = self.image.copy()
        out[self.selection] = self.original[self.selection]
        self._commit(out)

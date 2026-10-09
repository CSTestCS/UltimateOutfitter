"""HSV colour wheel with HEX input, and the palette editor dialog."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from ..core.colors import (extract_colors, extract_exact_colors, hex_to_rgb, hsv_to_rgb, is_valid_hex, rgb_to_hex,
                           rgb_to_hsv, sort_by_lightness)
from ..core.imaging import foreground_mask, load_rgba
from .common import IMAGE_FILTER, array_to_pixmap


class HSVWheel(QWidget):
    """Hue around the circle, saturation from centre to edge. Value is set externally."""

    picked = Signal(float, float)  # hue, saturation

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.h, self.s, self.v = 0.0, 100.0, 100.0
        self._cache: tuple[int, float, QPixmap] | None = None

    def set_hsv(self, h, s, v):
        self.h, self.s, self.v = h, s, v
        self.update()

    def _wheel(self, size: int) -> QPixmap:
        if self._cache and self._cache[0] == size and self._cache[1] == self.v:
            return self._cache[2]
        yy, xx = np.mgrid[:size, :size].astype(float)
        c = (size - 1) / 2
        dx, dy = xx - c, c - yy
        r = np.sqrt(dx * dx + dy * dy) / c
        hue = (np.degrees(np.arctan2(dy, dx)) % 360) / 60.0
        sat = np.clip(r, 0, 1)
        val = self.v / 100.0
        i = np.floor(hue).astype(int) % 6
        f = hue - np.floor(hue)
        p = val * (1 - sat)
        q = val * (1 - sat * f)
        t = val * (1 - sat * (1 - f))
        vv = np.full_like(f, val)
        rgb = np.dstack([np.choose(i, [vv, q, p, p, t, vv]),
                         np.choose(i, [t, vv, vv, q, p, p]),
                         np.choose(i, [p, p, t, vv, vv, q])])
        alpha = np.clip((1.0 - r) * c + 1, 0, 1) * 255
        img = np.dstack([rgb * 255, alpha]).astype(np.uint8)
        pm = array_to_pixmap(img)
        self._cache = (size, self.v, pm)
        return pm

    def paintEvent(self, e):
        size = min(self.width(), self.height())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ox, oy = (self.width() - size) // 2, (self.height() - size) // 2
        p.drawPixmap(ox, oy, self._wheel(size))
        c = size / 2
        ang = math.radians(self.h)
        rad = self.s / 100 * c
        x = ox + c + rad * math.cos(ang)
        y = oy + c - rad * math.sin(ang)
        p.setPen(QPen(QColor("black"), 2))
        p.drawEllipse(QPointF(x, y), 6, 6)
        p.setPen(QPen(QColor("white"), 1))
        p.drawEllipse(QPointF(x, y), 7.5, 7.5)
        p.end()

    def _pick(self, pos):
        size = min(self.width(), self.height())
        ox, oy = (self.width() - size) / 2, (self.height() - size) / 2
        c = size / 2
        dx, dy = pos.x() - ox - c, c - (pos.y() - oy)
        self.h = math.degrees(math.atan2(dy, dx)) % 360
        self.s = min(1.0, math.hypot(dx, dy) / c) * 100
        self.update()
        self.picked.emit(self.h, self.s)

    def mousePressEvent(self, e):
        self._pick(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons():
            self._pick(e.position())


class ColorPicker(QWidget):
    """Colour wheel + value slider + H/S/V, R/G/B and HEX inputs."""

    color_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wheel = HSVWheel()
        self.val_slider = QSlider(Qt.Orientation.Vertical)
        self.val_slider.setRange(0, 100)
        self.val_slider.setValue(100)
        self.val_slider.setToolTip("Value (brightness)")
        self.spins = {}
        form = QGridLayout()
        for row, (key, mx) in enumerate([("H", 360), ("S", 100), ("V", 100), ("R", 255), ("G", 255), ("B", 255)]):
            sp = QSpinBox()
            sp.setRange(0, mx)
            self.spins[key] = sp
            form.addWidget(QLabel(key), row % 3, (row // 3) * 2)
            form.addWidget(sp, row % 3, (row // 3) * 2 + 1)
        self.hex_edit = QLineEdit("#FF0000")
        self.hex_edit.setMaxLength(7)
        self.preview = QLabel()
        self.preview.setFixedHeight(36)
        form.addWidget(QLabel("HEX"), 3, 0)
        form.addWidget(self.hex_edit, 3, 1, 1, 3)
        form.addWidget(self.preview, 4, 0, 1, 4)
        top = QHBoxLayout()
        top.addWidget(self.wheel, 1)
        top.addWidget(self.val_slider)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addLayout(form)
        self._updating = False
        self.wheel.picked.connect(lambda h, s: self._set_hsv(h, s, self.val_slider.value()))
        self.val_slider.valueChanged.connect(lambda v: self._set_hsv(self.wheel.h, self.wheel.s, v))
        for k in "HSV":
            self.spins[k].valueChanged.connect(self._from_hsv_spins)
        for k in "RGB":
            self.spins[k].valueChanged.connect(self._from_rgb_spins)
        self.hex_edit.editingFinished.connect(self._from_hex)
        self.set_color("#FF0000")

    def color(self) -> str:
        return self.hex_edit.text().upper() if is_valid_hex(self.hex_edit.text()) else "#000000"

    def set_color(self, hexstr: str) -> None:
        h, s, v = rgb_to_hsv(hex_to_rgb(hexstr))
        self._set_hsv(h, s, v)

    def _set_hsv(self, h, s, v):
        if self._updating:
            return
        self._updating = True
        rgb = hsv_to_rgb(h, s, v)
        hx = rgb_to_hex(rgb)
        self.wheel.set_hsv(h, s, v)
        self.val_slider.setValue(int(round(v)))
        for k, val in zip("HSV", (h, s, v)):
            self.spins[k].setValue(int(round(val)))
        for k, val in zip("RGB", rgb):
            self.spins[k].setValue(val)
        self.hex_edit.setText(hx)
        self.preview.setStyleSheet(f"background:{hx}; border:1px solid #222;")
        self._updating = False
        self.color_changed.emit(hx)

    def _from_hsv_spins(self):
        if not self._updating:
            self._set_hsv(self.spins["H"].value(), self.spins["S"].value(), self.spins["V"].value())

    def _from_rgb_spins(self):
        if not self._updating:
            self.set_color(rgb_to_hex([self.spins[k].value() for k in "RGB"]))

    def _from_hex(self):
        txt = self.hex_edit.text().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        if is_valid_hex(txt):
            self.set_color(txt)


def color_icon(hexstr: str, size: int = 20) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(QColor(hexstr))
    return QIcon(pm)


class PaletteEditorDialog(QDialog):
    """Create or edit a palette: from a colour wheel, from an image, or both."""

    def __init__(self, parent=None, name: str = "", colors=None, kind: str = "varied",
                 source_image: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Palette editor")
        self.resize(820, 560)
        self.source_image = source_image
        self.picker = ColorPicker()
        self.name_edit = QLineEdit(name)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Varied hues", "varied")
        self.kind_combo.addItem("Shades of one colour", "shades")
        self.kind_combo.setCurrentIndex(0 if kind == "varied" else 1)
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.currentItemChanged.connect(self._on_select)
        btn_add = QPushButton("Add colour")
        btn_set = QPushButton("Replace selected")
        btn_del = QPushButton("Remove selected")
        btn_sort = QPushButton("Sort dark → light")
        btn_shades = QPushButton("Generate shades from picker…")
        btn_img = QPushButton("Extract from image…")
        self.n_colors = QSpinBox()
        self.n_colors.setRange(1, 256)
        self.n_colors.setValue(8)
        self.n_colors.setToolTip("How many colours to extract or generate")
        self.extract_mode = QComboBox()
        self.extract_mode.addItem("Exact pixel colours (precise)", "exact")
        self.extract_mode.addItem("Dominant colours (averaged clusters)", "cluster")
        self.extract_mode.setToolTip("Exact keeps the true HEX values found in the image; "
                                     "dominant averages similar pixels together")
        self.merge_tol = QDoubleSpinBox()
        self.merge_tol.setRange(0.0, 30.0)
        self.merge_tol.setSingleStep(0.5)
        self.merge_tol.setValue(0.0)
        self.merge_tol.setToolTip("Exact mode: colours closer than this (ΔE) to a more common colour are merged.\n"
                                  "0 = every distinct colour is kept exactly.")
        self.ignore_bg = QCheckBox("Ignore background")
        self.ignore_bg.setToolTip("Skip the border/background colour of an image (transparent pixels are always skipped)")
        btn_reextract = QPushButton("Re-extract")
        btn_reextract.clicked.connect(lambda: self.source_image and self.extract_from(self.source_image))
        self.extract_mode.currentIndexChanged.connect(
            lambda *_: self.merge_tol.setEnabled(self.extract_mode.currentData() == "exact"))
        btn_add.clicked.connect(lambda: self._add(self.picker.color()))
        btn_set.clicked.connect(self._replace)
        btn_del.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        btn_sort.clicked.connect(self._sort)
        btn_shades.clicked.connect(self._shades)
        btn_img.clicked.connect(self._extract_dialog)
        self.preview_img = QLabel()
        self.preview_img.setFixedHeight(120)
        self.preview_img.setAlignment(Qt.AlignmentFlag.AlignCenter)

        right = QVBoxLayout()
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Type", self.kind_combo)
        right.addLayout(form)
        right.addWidget(QLabel("Colours (drag to reorder):"))
        right.addWidget(self.list, 1)
        row = QHBoxLayout()
        for b in (btn_add, btn_set, btn_del, btn_sort):
            row.addWidget(b)
        right.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(btn_shades)
        row2.addWidget(btn_img)
        row2.addWidget(QLabel("Count:"))
        row2.addWidget(self.n_colors)
        right.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(self.extract_mode, 1)
        row3.addWidget(QLabel("Merge ΔE:"))
        row3.addWidget(self.merge_tol)
        row3.addWidget(self.ignore_bg)
        row3.addWidget(btn_reextract)
        right.addLayout(row3)
        right.addWidget(self.preview_img)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        lay = QHBoxLayout(self)
        lay.addWidget(self.picker, 1)
        lay.addLayout(right, 1)
        for c in colors or []:
            self._add(c)
        if source_image:
            self._show_source(source_image)

    # helpers -----------------------------------------------------------------
    def _add(self, hexstr: str):
        it = QListWidgetItem(color_icon(hexstr), hexstr)
        self.list.addItem(it)

    def _replace(self):
        it = self.list.currentItem()
        if it:
            c = self.picker.color()
            it.setText(c)
            it.setIcon(color_icon(c))

    def _on_select(self, cur, _prev):
        if cur:
            self.picker.set_color(cur.text())

    def _sort(self):
        cols = sort_by_lightness(self.colors())
        self.list.clear()
        for c in cols:
            self._add(c)

    def _shades(self):
        """Shades from dark to light; hue drifts slightly (warmer highlights, cooler shadows)."""
        h, s, v = rgb_to_hsv(hex_to_rgb(self.picker.color()))
        n = self.n_colors.value()
        self.list.clear()
        for i in range(n):
            t = i / max(n - 1, 1)
            hh = (h + (t - 0.5) * 16) % 360
            ss = max(5.0, min(100.0, s * (1.15 - 0.5 * t)))
            vv = 18 + t * 80
            self._add(rgb_to_hex(hsv_to_rgb(hh, ss, vv)))
        self.kind_combo.setCurrentIndex(1)

    def _extract_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Extract palette from image", "", IMAGE_FILTER)
        if path:
            self.extract_from(path)

    def extract_from(self, path: str):
        img = load_rgba(path)
        mask = img[..., 3] > 16
        if self.ignore_bg.isChecked():
            mask &= foreground_mask(img, tolerance=0.5 if self.extract_mode.currentData() == "exact" else 12)
        if self.extract_mode.currentData() == "exact":
            cols = extract_exact_colors(img[..., :3], self.n_colors.value(), mask, self.merge_tol.value())
        else:
            cols = extract_colors(img[..., :3], self.n_colors.value(), mask)
        self.list.clear()
        for rgb, _share in cols:
            self._add(rgb_to_hex(rgb))
        self.source_image = path
        self._show_source(path)
        if not self.name_edit.text():
            self.name_edit.setText(Path(path).stem)

    def _show_source(self, path):
        pm = QPixmap(path)
        if not pm.isNull():
            self.preview_img.setPixmap(pm.scaled(300, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))

    def colors(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def kind(self) -> str:
        return self.kind_combo.currentData()

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Palette", "Please give the palette a name.")
            return
        if not self.colors():
            QMessageBox.warning(self, "Palette", "Add at least one colour.")
            return
        self.accept()

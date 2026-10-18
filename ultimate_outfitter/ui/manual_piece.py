"""Wardrobe creator: add one specific piece, choosing the item, palettes, print and options by hand."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QSpinBox, QVBoxLayout)

from ..core.character import Character
from ..core.imaging import shine_kind
from .common import array_to_pixmap, palette_pixmap, thumb_cache

PREVIEW = 360


class ManualPieceDialog(QDialog):
    """Pick an item, 1-3 palettes, an optional print and the generation options; preview, then add."""

    def __init__(self, parent, character: Character):
        super().__init__(parent)
        self.character = character
        self.lib = character.library
        self.cache: dict = {}
        self.entry: dict | None = None
        self.setWindowTitle(f"Add a piece to {character.name}'s wardrobe")
        gs = character.data.get("gen_settings", {})
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.render_preview)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter items…")
        self.search.textChanged.connect(self._fill_items)
        self.item = QComboBox()
        self.item.setIconSize(QSize(32, 32))
        self.item.currentIndexChanged.connect(self._item_changed)
        self.item_info = QLabel()
        self.item_info.setWordWrap(True)

        self.pal = [QComboBox() for _ in range(3)]
        palettes = sorted(self.lib.palettes.values(), key=lambda p: p["name"].lower())
        for i, combo in enumerate(self.pal):
            combo.setIconSize(palette_pixmap(["#000"], 90, 14).size())
            if i:
                combo.addItem("(none)", None)
            for p in palettes:
                combo.addItem(QIcon(palette_pixmap(p["colors"], 90, 14)), p["name"], p["id"])
            combo.currentIndexChanged.connect(self._changed)
        # start from the character's best-matching palettes
        matched = [p["id"] for p in character.matched_palettes()] if hasattr(character, "matched_palettes") else []
        if matched:
            self.pal[0].setCurrentIndex(max(0, self.pal[0].findData(matched[0])))

        self.pattern = QComboBox()
        self.pattern.addItem("(no print)", None)
        for p in sorted(self.lib.patterns.values(), key=lambda p: p["name"].lower()):
            self.pattern.addItem(QIcon(thumb_cache.get(self.lib.abspath(p["image"]), 24)), p["name"], p["id"])
        self.pattern.currentIndexChanged.connect(self._pattern_changed)
        self.placement = QComboBox()
        self.placement.addItem("Pattern's own setting", None)
        self.placement.addItem("Main colour only", "primary")
        self.placement.addItem("Whole piece", "whole")
        self.placement.currentIndexChanged.connect(self._changed)
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 60)
        self.repeats.setValue(6)
        self.repeats.setToolTip("How many times the pattern repeats across the piece (bigger = smaller print)")
        self.repeats.valueChanged.connect(self._changed)

        self.lock = QCheckBox("Lock to the exact palette colours / shades")
        self.lock.setChecked(gs.get("lock_palette", True))
        self.lock.toggled.connect(self._changed)
        self.auto_print = QCheckBox("Add a print when a palette has nothing to colour")
        self.auto_print.setChecked(True)
        self.auto_print.toggled.connect(self._changed)
        self.shine = QComboBox()
        self.shine.addItem("Automatic (from palette / item names)", None)
        self.shine.addItem("None", "none")
        for kind in ("metallic", "silk"):
            for g in range(3):
                self.shine.addItem(f"{kind.title()} on palette {g + 1}", (kind, g))
        self.shine.setToolTip("Which parts the 3D preview makes shiny (the texture itself is never shaded)")
        self.shine.currentIndexChanged.connect(self._changed)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(PREVIEW, PREVIEW)
        self.preview_note = QLabel()
        self.preview_note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Find", self.search)
        form.addRow("Item", self.item)
        form.addRow("", self.item_info)
        form.addRow("Palette 1", self.pal[0])
        form.addRow("Palette 2", self.pal[1])
        form.addRow("Palette 3", self.pal[2])
        form.addRow("Print", self.pattern)
        form.addRow("Print placement", self.placement)
        form.addRow("Print repeats", self.repeats)
        form.addRow("Shine (3D preview)", self.shine)
        form.addRow(self.lock)
        form.addRow(self.auto_print)
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.preview_note)
        row = QHBoxLayout()
        row.addLayout(form, 1)
        row.addLayout(right, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_add = bb.addButton("Add to wardrobe", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.accepted.connect(self.add)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(row, 1)
        lay.addWidget(bb)
        self._fill_items()
        self._restore_last()

    # ------------------------------------------------------------ remembered options
    LAST_KEY = "manual_piece_last"

    def _restore_last(self):
        """Start from the options used for the last piece added (missing items / palettes are skipped)."""
        last = self.character.data.get(self.LAST_KEY)
        if not last:
            return

        def norm(v):
            return list(v) if isinstance(v, (list, tuple)) else v

        def choose(combo, value):
            for i in range(combo.count()):
                if norm(combo.itemData(i)) == norm(value):
                    combo.setCurrentIndex(i)
                    return

        if last.get("item") in self.lib.items:
            choose(self.item, last["item"])
        for combo, pid in zip(self.pal, (last.get("palettes") or []) + [None, None, None]):
            if pid is None or pid in self.lib.palettes:
                choose(combo, pid)
        if last.get("pattern") is None or last["pattern"] in self.lib.patterns:
            choose(self.pattern, last.get("pattern"))
        choose(self.placement, last.get("placement"))
        if last.get("repeats"):
            self.repeats.setValue(int(last["repeats"]))      # after the pattern, which resets it
        choose(self.shine, last.get("shine"))
        if "lock" in last:
            self.lock.setChecked(bool(last["lock"]))
        if "auto_print" in last:
            self.auto_print.setChecked(bool(last["auto_print"]))

    def _remember(self):
        self.character.data[self.LAST_KEY] = {
            "item": self.item.currentData(),
            "palettes": [c.currentData() for c in self.pal],
            "pattern": self.pattern.currentData(),
            "placement": self.placement.currentData(),
            "repeats": self.repeats.value(),
            "shine": list(self.shine.currentData()) if isinstance(self.shine.currentData(), (list, tuple))
            else self.shine.currentData(),
            "lock": self.lock.isChecked(),
            "auto_print": self.auto_print.isChecked(),
        }

    # ------------------------------------------------------------ choices
    def _fill_items(self, *_):
        cur = self.item.currentData()
        text = self.search.text().strip().lower()
        self.item.blockSignals(True)
        self.item.clear()
        items = sorted(self.lib.items.values(), key=lambda i: (i["category"], i["name"].lower()))
        for it in items:
            label = f"{it['name']} ({it['category']})"
            if text and text not in label.lower():
                continue
            self.item.addItem(QIcon(thumb_cache.get(self.lib.abspath(it["image"]), 32)), label, it["id"])
        self.item.setCurrentIndex(max(0, self.item.findData(cur)))
        self.item.blockSignals(False)
        self._item_changed()

    def _item_changed(self, *_):
        item = self.lib.items.get(self.item.currentData())
        if item:
            score = self.character.rate_item(item)
            n = len(self.lib.item_images(item))
            self.item_info.setText(f"Personality match: {score:.0f}%" + (f" — {n} images" if n > 1 else ""))
        else:
            self.item_info.setText("Add clothing items in A. Collection first.")
        self._changed()

    def _pattern_changed(self, *_):
        pat = self.lib.patterns.get(self.pattern.currentData())
        if pat:
            self.repeats.blockSignals(True)
            self.repeats.setValue(int(pat.get("attrs", {}).get("repeats", 6)))
            self.repeats.blockSignals(False)
        self._changed()

    def _changed(self, *_):
        self._timer.start()

    def plan_piece(self) -> dict | None:
        item = self.lib.items.get(self.item.currentData())
        palettes = [self.lib.palettes.get(c.currentData()) for c in self.pal]
        palettes = [p for p in palettes if p]
        if not item or not palettes:
            return None
        pattern = self.lib.patterns.get(self.pattern.currentData())
        if pattern:
            attrs = dict(pattern.get("attrs", {}), repeats=self.repeats.value())
            if self.placement.currentData():
                attrs["placement"] = self.placement.currentData()
            pattern = dict(pattern, attrs=attrs)
        if self.placement.currentData() == "whole" and pattern:
            item = dict(item, attrs=dict(item.get("attrs", {}), print="whole"))
        elif self.placement.currentData() == "primary" and pattern:
            item = dict(item, attrs=dict(item.get("attrs", {}), print="primary"))
        return {"item": item, "palettes": palettes, "pattern": pattern,
                "score": self.character.rate_item(self.lib.items[item["id"]]),
                "lock": self.lock.isChecked(), "auto_pattern": self.auto_print.isChecked(),
                "shine": self.shine.currentData(), "custom": True, "print_scale": 1.0}

    # ------------------------------------------------------------ preview / add
    def render_preview(self):
        piece = self.plan_piece()
        self.b_add.setEnabled(piece is not None)
        if not piece:
            self.preview.setText("Choose an item and at least one palette.")
            self.preview_note.clear()
            return
        info: dict = {}
        shine: list = []
        try:
            outs = self.character.render_piece(piece["item"], piece["palettes"], piece["pattern"], self.cache,
                                               shine_out=shine, info_out=info, lock=piece["lock"],
                                               auto_pattern=piece["auto_pattern"], shine=piece["shine"],
                                               print_scale=piece["print_scale"])
        except OSError as exc:
            self.preview.setText(f"Preview failed: {exc}")
            return
        self.preview.setPixmap(array_to_pixmap(outs[0]).scaled(
            PREVIEW, PREVIEW, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        notes = []
        if info.get("pattern"):
            notes.append(f"Print “{info['pattern']['name']}” added so every palette is used.")
        kinds = sorted({k for applied in shine for _m, k in applied})
        if kinds:
            notes.append("Shiny in the 3D preview: " + ", ".join(kinds) + ".")
        elif any(shine_kind(p["name"]) for p in piece["palettes"]) and piece["shine"] == "none":
            notes.append("No shine (set to None).")
        self.preview_note.setText(" ".join(notes))

    def add(self):
        piece = self.plan_piece()
        if not piece:
            return
        try:
            created = self.character.build_wardrobe(item_ids=[], plan=[piece])
        except OSError as exc:
            QMessageBox.warning(self, "Add piece", f"Could not create the piece: {exc}")
            return
        if not created:
            QMessageBox.warning(self, "Add piece", "The piece could not be created (is the item image missing?).")
            return
        self.entry = created[0]
        self._remember()
        self.character.save()
        self.accept()

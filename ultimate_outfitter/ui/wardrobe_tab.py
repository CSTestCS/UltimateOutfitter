"""Character wardrobe creator: profiles, palette scan and automatic wardrobe building."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QScrollArea, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSlider, QSpinBox,
                               QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..core.categories import CATEGORY_NAMES
from ..core.character import BRA_CHOICES, CHARACTER_QUESTIONS, Character, evaluate_character, list_characters
from ..core.colors import precision_to_threshold
from ..core.traits import describe
from .common import IMAGE_FILTER, AppState, Gallery, SwatchRow, palette_pixmap, run_with_progress, thumb_cache
from .questionnaire import QuestionForm


def open_folder(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


class CharacterDialog(QDialog):
    def __init__(self, parent=None, character: Character | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit character" if character else "New character")
        self.resize(1050, 780)
        self.image_paths: list[str] = []
        data = character.data if character else {}
        prefs = data.get("prefs", {})
        self.name = QLineEdit(data.get("name", ""))
        self.name.setReadOnly(character is not None)
        self.img_label = QLabel("No image")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setMinimumSize(240, 240)
        b_img = QPushButton("Choose character image(s)…")
        b_img.setToolTip("Several images (outfits, angles, art styles) can be used; the palette scan uses all of them.")
        b_img.clicked.connect(self._choose)
        b_img.setVisible(character is None)
        self.img_count = QLabel("")
        if character:
            self.img_label.setPixmap(thumb_cache.get(character.image_path, 240))
        self.bra = QComboBox()
        self.bra.addItems(BRA_CHOICES)
        self.bra.setCurrentText(prefs.get("wears_bra", "Yes"))
        self.swim_sub = QCheckBox("Underwear && bras also count as swimwear")
        self.swim_sub.setChecked(prefs.get("underwear_as_swimwear", True))
        self.acc = QSpinBox()
        self.acc.setRange(0, 8)
        self.acc.setValue(prefs.get("accessory_level", 3))
        self.excluded = QListWidget()
        for c in CATEGORY_NAMES:
            it = QListWidgetItem(c)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if c in prefs.get("excluded_categories", [])
                             else Qt.CheckState.Checked)
            self.excluded.addItem(it)
        self.traits = QLabel()
        self.traits.setWordWrap(True)
        self.form = QuestionForm(CHARACTER_QUESTIONS)
        self.form.changed.connect(self._update)
        if data.get("answers"):
            self.form.set_answers(data["answers"])

        left = QVBoxLayout()
        f = QFormLayout()
        f.addRow("Name", self.name)
        left.addLayout(f)
        left.addWidget(self.img_label)
        left.addWidget(b_img)
        left.addWidget(self.img_count)
        f2 = QFormLayout()
        f2.addRow("Wears bras?", self.bra)
        f2.addRow(self.swim_sub)
        f2.addRow("Max accessories per outfit", self.acc)
        left.addLayout(f2)
        left.addWidget(QLabel("Categories this character wears:"))
        left.addWidget(self.excluded, 1)
        left.addWidget(QLabel("<b>Personality profile:</b>"))
        left.addWidget(self.traits)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(330)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        right = QVBoxLayout()
        right.addWidget(self.form, 1)
        right.addWidget(buttons)
        lay = QHBoxLayout(self)
        lay.addWidget(lw)
        lay.addLayout(right, 1)
        self._update()

    def _choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Character image(s)", "", IMAGE_FILTER)
        if paths:
            self.image_paths = paths
            path = paths[0]
            self.img_count.setText(f"{len(paths)} image(s) selected" if len(paths) > 1 else "")
            pm = QPixmap(path)
            self.img_label.setPixmap(pm.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            if not self.name.text():
                self.name.setText(Path(path).stem)

    def _update(self):
        traits, _ = evaluate_character(self.form.answers())
        self.traits.setText(describe(traits, 10) or "(answer the questions)")

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Character", "Please enter a name.")
            return
        if not self.name.isReadOnly() and not self.image_paths:
            QMessageBox.warning(self, "Character", "Please choose a character image.")
            return
        if self.form.unanswered() and QMessageBox.question(
                self, "Character", "Some questions are unanswered. Save anyway?") != QMessageBox.StandardButton.Yes:
            return
        self.accept()

    def prefs(self) -> dict:
        excluded = [self.excluded.item(i).text() for i in range(self.excluded.count())
                    if self.excluded.item(i).checkState() != Qt.CheckState.Checked]
        return {"wears_bra": self.bra.currentText(), "accessory_level": self.acc.value(),
                "underwear_as_swimwear": self.swim_sub.isChecked(),
                "excluded_categories": excluded}


class WardrobeTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.character: Character | None = None

        # ---- character list
        self.char_list = Gallery(96)
        self.char_list.currentItemChanged.connect(self._select_character)
        b_new = QPushButton("New character…")
        b_new.clicked.connect(self.new_character)
        b_open = QPushButton("Open profile file…")
        b_open.clicked.connect(self.open_profile)
        lv = QVBoxLayout()
        lv.addWidget(QLabel("<b>Characters</b>"))
        lv.addWidget(self.char_list, 1)
        lv.addWidget(b_new)
        lv.addWidget(b_open)
        lw = QWidget()
        lw.setLayout(lv)

        # ---- profile header
        self.portrait = QLabel()
        self.portrait.setFixedSize(180, 180)
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info = QLabel("Create or select a character.")
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        b_edit = QPushButton("Edit profile…")
        b_edit.clicked.connect(self.edit_character)
        b_folder = QPushButton("Open character folder")
        b_folder.clicked.connect(lambda: self.character and open_folder(self.character.dir))
        hb = QVBoxLayout()
        b_img_add = QPushButton("Add reference image…")
        b_img_add.setToolTip("More images of this character to base colour palettes on")
        b_img_add.clicked.connect(self.add_reference_image)
        b_img_rem = QPushButton("Remove a reference image…")
        b_img_rem.clicked.connect(self.remove_reference_image)
        hb.addWidget(b_edit)
        hb.addWidget(b_img_add)
        hb.addWidget(b_img_rem)
        hb.addWidget(b_folder)
        hb.addStretch(1)
        header = QHBoxLayout()
        header.addWidget(self.portrait)
        header.addWidget(self.info, 1)
        header.addLayout(hb)

        # ---- palette scan
        scan_box = QGroupBox("1. Palette scan")
        sl = QVBoxLayout(scan_box)
        self.precision = QSlider(Qt.Orientation.Horizontal)
        self.precision.setRange(0, 100)
        self.precision.setValue(60)
        self.precision_label = QLabel()
        self.precision.valueChanged.connect(self._precision_text)
        self.coverage = QSpinBox()
        self.coverage.setRange(5, 100)
        self.coverage.setSuffix(" %")
        self.coverage.setValue(50)
        self.coverage.setToolTip("How many of a palette's colours must be found in the character image")
        self.n_colors = QSpinBox()
        self.n_colors.setRange(4, 48)
        self.n_colors.setValue(16)
        b_scan = QPushButton("Scan character image for matching palettes")
        b_scan.clicked.connect(self.scan)
        self.image_colors = SwatchRow(size=18)
        self.matches = QListWidget()
        self.matches.setIconSize(palette_pixmap(["#000"], 160, 18).size())
        self.matches.itemChanged.connect(self._match_toggled)
        f = QFormLayout()
        f.addRow("Precision (loose ↔ exact)", self.precision)
        f.addRow("", self.precision_label)
        f.addRow("Min. palette coverage", self.coverage)
        f.addRow("Colours sampled from image", self.n_colors)
        sl.addLayout(f)
        sl.addWidget(b_scan)
        sl.addWidget(QLabel("Colours found in the character:"))
        sl.addWidget(self.image_colors)
        sl.addWidget(QLabel("Matching palettes (untick to leave one out):"))
        sl.addWidget(self.matches, 1)

        # ---- generation
        gen_box = QGroupBox("2. Build wardrobe")
        gl = QVBoxLayout(gen_box)
        self.min_score = QSpinBox()
        self.min_score.setRange(0, 100)
        self.min_score.setValue(35)
        self.max_items = QSpinBox()
        self.max_items.setRange(1, 200)
        self.max_items.setValue(6)
        self.max_items.setToolTip("How many different base items of one category may be owned")
        self.size = QComboBox()
        for label, v in (("Minimalist (×0.4)", 0.4), ("Small (×0.7)", 0.7), ("Average (×1)", 1.0),
                         ("Large (×1.6)", 1.6), ("Fashionista (×2.5)", 2.5), ("Hoarder (×4)", 4.0)):
            self.size.addItem(label, v)
        self.size.setToolTip("Scales how many pieces per slot a realistic wardrobe gets "
                             "(average: ~10 tops, 7 bottoms, 4 pairs of shoes...)")
        self.max_colourways = QSpinBox()
        self.max_colourways.setRange(1, 20)
        self.max_colourways.setToolTip("The most versions (colours / prints) of a single item; only great "
                                       "matches reach the maximum")
        self.multi_chance = self._pct("Chance a piece mixes two palettes")
        self.triple_chance = self._pct("Chance a piece mixes three palettes")
        self.pattern_chance = self._pct("Chance a piece gets a print (when a suitable pattern exists)")
        self.fav_bias = self._pct("0% = every matched palette equally likely, 100% = mostly the best matches")
        self.rating_bias = self._pct("0% = every suitable item equally likely, 100% = mostly the best matches")
        self.exhaustive = QCheckBox("Exhaustive: every item in every palette (not realistic)")
        self.seed_label = QLabel()
        b_seed = QPushButton("New random seed")
        b_seed.setToolTip("Builds use a stored random seed; change it for a different selection")
        b_seed.clicked.connect(self._new_seed)
        self.patterns_list = QListWidget()
        self.patterns_list.setMaximumHeight(90)
        self.patterns_list.setToolTip("Untick patterns this character should never wear")
        gf = QFormLayout()
        gf.addRow("Minimum personality match", self.min_score)
        gf.addRow("Wardrobe size", self.size)
        gf.addRow("Max items per category", self.max_items)
        gf.addRow("Max versions per item", self.max_colourways)
        gf.addRow("Two-palette pieces", self.multi_chance)
        gf.addRow("Three-palette pieces", self.triple_chance)
        gf.addRow("Printed pieces", self.pattern_chance)
        gf.addRow("Favourite-palette bias", self.fav_bias)
        gf.addRow("Best-match item bias", self.rating_bias)
        seed_row = QHBoxLayout()
        seed_row.addWidget(self.seed_label, 1)
        seed_row.addWidget(b_seed)
        gf.addRow("Random seed", seed_row)
        gf.addRow(self.exhaustive)
        gf.addRow("Allowed patterns", self.patterns_list)
        gl.addLayout(gf)
        b_build = QPushButton("Build / update wardrobe (all items)")
        b_build.clicked.connect(lambda: self.build(new_only=False))
        self.b_new = QPushButton("Scan for new clothing items")
        self.b_new.clicked.connect(lambda: self.build(new_only=True))
        b_clear = QPushButton("Clear wardrobe…")
        b_clear.setToolTip("Delete every generated piece so the wardrobe can be rebuilt from scratch")
        b_clear.clicked.connect(self.clear_wardrobe)
        gl.addWidget(b_build)
        gl.addWidget(self.b_new)
        gl.addWidget(b_clear)
        self.ratings = QTreeWidget()
        self.ratings.setHeaderLabels(["Category / item", "Match"])
        self.ratings.setColumnWidth(0, 230)
        self.ratings.setMinimumHeight(160)
        gl.addWidget(QLabel("Item ratings for this character (best first):"))
        gl.addWidget(self.ratings, 1)

        # ---- wardrobe gallery
        self.gallery = Gallery(128)
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.filter = QComboBox()
        self.filter.addItem("All categories")
        self.filter.addItems(CATEGORY_NAMES)
        self.filter.currentIndexChanged.connect(self.refresh_gallery)
        self.count_label = QLabel()
        b_ed = QPushButton("Open in editor")
        b_ed.clicked.connect(self._open_editor)
        b_del = QPushButton("Remove from wardrobe")
        b_del.clicked.connect(self._remove_entries)
        gb = QHBoxLayout()
        gb.addWidget(self.filter)
        gb.addWidget(self.count_label, 1)
        gb.addWidget(b_ed)
        gb.addWidget(b_del)
        gal = QWidget()
        gv = QVBoxLayout(gal)
        gv.addLayout(gb)
        gv.addWidget(self.gallery)

        setup = QWidget()
        sh = QHBoxLayout(setup)
        sh.addWidget(scan_box, 1)
        sh.addWidget(gen_box, 1)
        self.tabs = QTabWidget()
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setWidget(setup)
        self.tabs.addTab(setup_scroll, "Scan && build")
        self.tabs.addTab(gal, "Wardrobe")

        rv = QVBoxLayout()
        rv.addLayout(header)
        rv.addWidget(self.tabs, 1)
        rw = QWidget()
        rw.setLayout(rv)
        split = QSplitter()
        split.addWidget(lw)
        split.addWidget(rw)
        split.setStretchFactor(1, 4)
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        state.characters_changed.connect(self.refresh_characters)
        state.library_changed.connect(self._library_changed)
        self._precision_text(60)
        self.refresh_characters()

    # ---------------------------------------------------------------- characters
    def refresh_characters(self, select_dir: Path | None = None):
        current = select_dir or (self.character.dir if self.character else None)
        self.char_list.blockSignals(True)
        self.char_list.clear()
        chosen = None
        for ch in list_characters(self.state.library):
            it = self.char_list.add(str(ch.path), ch.name, ch.image_path)
            if current and ch.dir == current:
                chosen = it
        self.char_list.blockSignals(False)
        if chosen:
            self.char_list.setCurrentItem(chosen)
        elif self.char_list.count() and not self.character:
            self.char_list.setCurrentRow(0)
        else:
            self._select_character()

    def _select_character(self, *_):
        key = self.char_list.current_key()
        if not key:
            self.character = None
            self._show_character()
            return
        try:
            self.character = Character(self.state.library, Path(key))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Character", f"Could not open profile: {exc}")
            self.character = None
        self._show_character()

    def _library_changed(self):
        if self.character:
            self._show_character()

    def _show_character(self):
        ch = self.character
        if ch is None:
            self.portrait.clear()
            self.info.setText("Create or select a character.")
            self.matches.clear()
            self.gallery.clear()
            self.ratings.clear()
            return
        self.portrait.setPixmap(thumb_cache.get(ch.image_path, 180))
        prefs = ch.data.get("prefs", {})
        excl = prefs.get("excluded_categories", [])
        self.info.setText(
            f"<h2>{ch.name}</h2><b>Personality:</b> {describe(ch.traits, 10)}<br>"
            f"<b>Wears bras:</b> {prefs.get('wears_bra', 'Yes')} &nbsp; "
            f"<b>Accessories:</b> up to {prefs.get('accessory_level', 3)}<br>"
            f"<b>Excluded categories:</b> {', '.join(excl) if excl else 'none'}<br>"
            f"<b>Reference images:</b> {len(ch.data.get('images', [1]))}<br>"
            f"<b>Wardrobe:</b> {len(ch.data['wardrobe'])} pieces "
            f"({len(ch.data['dresser'])} in dresser, {len(ch.data['hamper'])} in hamper)")
        scan = ch.data["palette_scan"]
        for w, v in ((self.precision, scan.get("precision", 60)),
                     (self.coverage, int(scan.get("min_coverage", 0.5) * 100)),
                     (self.n_colors, scan.get("n_colors", 16))):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self._precision_text(self.precision.value())
        gs = ch.data.get("gen_settings", {})
        self.min_score.setValue(gs.get("min_score", 35))
        self.max_items.setValue(gs.get("max_items_per_category", 6))
        idx = min(range(self.size.count()), key=lambda i: abs(self.size.itemData(i) - gs.get("wardrobe_size", 1.0)))
        self.size.setCurrentIndex(idx)
        self.max_colourways.setValue(gs.get("max_colourways", 3))
        for w, key in ((self.multi_chance, "multi_palette_chance"), (self.triple_chance, "triple_palette_chance"),
                       (self.pattern_chance, "pattern_chance"), (self.fav_bias, "favourite_bias"),
                       (self.rating_bias, "rating_bias")):
            w.setValue(int(round(gs.get(key, 0) * 100)))
        self.exhaustive.setChecked(gs.get("exhaustive", False))
        self.seed_label.setText(str(gs.get("seed", 1)))
        excluded = set(gs.get("excluded_patterns", []))
        self.patterns_list.clear()
        for pat in sorted(self.state.library.patterns.values(), key=lambda p: p["name"].lower()):
            it = QListWidgetItem(QIcon(thumb_cache.get(self.state.library.abspath(pat["image"]), 24)), pat["name"])
            it.setData(Qt.ItemDataRole.UserRole, pat["id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if pat["id"] in excluded else Qt.CheckState.Checked)
            self.patterns_list.addItem(it)
        self.image_colors.set_colors([c for c, _ in scan.get("image_colors", [])])
        self._fill_matches()
        n_new = len(ch.new_item_ids())
        self.b_new.setText(f"Scan for new clothing items ({n_new} new)")
        self._fill_ratings()
        self.refresh_gallery()

    def _fill_matches(self):
        ch = self.character
        self.matches.blockSignals(True)
        self.matches.clear()
        excluded = set(ch.data["palette_scan"].get("excluded", []))
        for m in ch.data["palette_scan"].get("matches", []):
            pal = self.state.library.palettes.get(m["palette_id"])
            if not pal:
                continue
            it = QListWidgetItem(QIcon(palette_pixmap(pal["colors"], 160, 18)),
                                 f"  {pal['name']}  — {m['coverage']:.0%} found, avg ΔE {m['distance']:.1f}")
            it.setData(Qt.ItemDataRole.UserRole, pal["id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if pal["id"] in excluded else Qt.CheckState.Checked)
            self.matches.addItem(it)
        self.matches.blockSignals(False)

    def _match_toggled(self, item):
        ch = self.character
        if not ch:
            return
        excluded = set(ch.data["palette_scan"].get("excluded", []))
        pid = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            excluded.discard(pid)
        else:
            excluded.add(pid)
        ch.data["palette_scan"]["excluded"] = sorted(excluded)
        ch.save()

    def _fill_ratings(self):
        self.ratings.clear()
        ch = self.character
        ranked = ch.rank_items()
        for cat in CATEGORY_NAMES:
            if cat not in ranked:
                continue
            top = QTreeWidgetItem([f"{cat} ({len(ranked[cat])})", ""])
            for item, score in ranked[cat]:
                child = QTreeWidgetItem([item["name"], f"{score:.0f}"])
                child.setIcon(0, QIcon(thumb_cache.get(self.state.library.abspath(item["image"]), 32)))
                top.addChild(child)
            self.ratings.addTopLevelItem(top)

    def _precision_text(self, v):
        self.precision_label.setText(f"colour distance threshold ΔE ≤ {precision_to_threshold(v):.1f}")

    def new_character(self):
        dlg = CharacterDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ch = Character.create(self.state.library, dlg.name.text().strip(), dlg.image_paths,
                              dlg.form.answers(), dlg.prefs())
        self.character = ch
        self.refresh_characters(ch.dir)
        self.state.characters_changed.emit()
        if self.state.library.palettes:
            self.scan()

    def edit_character(self):
        if not self.character:
            return
        dlg = CharacterDialog(self, self.character)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.character.update_answers(dlg.form.answers(), dlg.prefs())
            self._show_character()
            self.state.characters_changed.emit()

    def open_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open character profile",
                                              str(self.state.library.characters_dir()), "Profile (profile.json)")
        if not path:
            return
        p = Path(path)
        if p.parent.parent != self.state.library.characters_dir():
            QMessageBox.information(self, "Open profile",
                                    "Profiles must live inside the library's Characters folder. "
                                    "Copy the character folder there, then reopen it.")
            return
        self.refresh_characters(p.parent)

    # ------------------------------------------------------------- scan / build
    def _save_settings(self):
        ch = self.character
        gs = ch.data["gen_settings"]
        gs["min_score"] = self.min_score.value()
        gs["max_items_per_category"] = self.max_items.value()
        gs["wardrobe_size"] = self.size.currentData()
        gs["max_colourways"] = self.max_colourways.value()
        gs["multi_palette_chance"] = self.multi_chance.value() / 100
        gs["triple_palette_chance"] = self.triple_chance.value() / 100
        gs["pattern_chance"] = self.pattern_chance.value() / 100
        gs["favourite_bias"] = self.fav_bias.value() / 100
        gs["rating_bias"] = self.rating_bias.value() / 100
        gs["exhaustive"] = self.exhaustive.isChecked()
        gs["excluded_patterns"] = [self.patterns_list.item(i).data(Qt.ItemDataRole.UserRole)
                                   for i in range(self.patterns_list.count())
                                   if self.patterns_list.item(i).checkState() != Qt.CheckState.Checked]
        ch.save()

    def _pct(self, tip: str) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(0, 100)
        sp.setSuffix(" %")
        sp.setToolTip(tip)
        return sp

    def _new_seed(self):
        if self.character:
            import random
            self.character.data["gen_settings"]["seed"] = random.randrange(1, 1 << 30)
            self.character.save()
            self.seed_label.setText(str(self.character.data["gen_settings"]["seed"]))

    def add_reference_image(self):
        ch = self.character
        if not ch:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, f"More images of {ch.name}", "", IMAGE_FILTER)
        for p in paths:
            ch.add_image(p)
        if paths:
            self._show_character()
            if self.state.library.palettes:
                self.scan()

    def remove_reference_image(self):
        ch = self.character
        if not ch or len(ch.data["images"]) < 2:
            QMessageBox.information(self, "Reference images", "A character needs at least one image.")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "Remove reference image", "Image to stop using:",
                                        ch.data["images"], 0, False)
        if ok and name:
            ch.remove_image(name)
            self._show_character()

    def clear_wardrobe(self):
        ch = self.character
        if not ch or not ch.data["wardrobe"]:
            return
        r = QMessageBox.question(self, "Clear wardrobe", f"Delete all {len(ch.data['wardrobe'])} generated pieces "
                                 f"of {ch.name} (and their image files)?\nOutfit history is kept.")
        if r == QMessageBox.StandardButton.Yes:
            for eid in list(ch.data["wardrobe"]):
                ch.remove_entry(eid, delete_file=True)
            ch.data["processed_items"] = []
            ch.data.pop("current_outfit", None)
            ch.save()
            self._show_character()
            self.state.characters_changed.emit()

    def scan(self):
        ch = self.character
        if not ch:
            return
        if not self.state.library.palettes:
            QMessageBox.information(self, "Scan", "There are no palettes in the library yet.")
            return

        def done(matches):
            self._show_character()
            if not matches:
                QMessageBox.information(self, "Scan", "No palettes matched. Try lowering the precision "
                                        "or the minimum coverage.")
        run_with_progress(self, "Scanning palettes", ch.scan_palettes, self.precision.value(),
                          self.coverage.value() / 100, self.n_colors.value(), on_done=done)

    def build(self, new_only: bool):
        ch = self.character
        if not ch:
            return
        self._save_settings()
        if not ch.data["palette_scan"].get("matches"):
            QMessageBox.information(self, "Build", "Run the palette scan first (no matching palettes yet).")
            return
        ids = ch.new_item_ids() if new_only else None
        if new_only and not ids:
            QMessageBox.information(self, "Scan for new items", "No new clothing items since the last build.")
            return
        plan = ch.plan_wardrobe(ids)
        if not plan:
            QMessageBox.information(self, "Build", "Nothing new to create: no items reach the minimum match, "
                                    "or every recolour already exists.")
            if ids:
                ch.data["processed_items"] = sorted(set(ch.data["processed_items"]) | set(ids))
                ch.save()
            self._show_character()
            return
        summary = ch.plan_summary(plan)
        multi = sum(len(p["palettes"]) > 1 for p in plan)
        printed = sum(p["pattern"] is not None for p in plan)
        lines = "\n".join(f"  {cat}: {n}" for cat, n in sorted(summary.items()))
        if QMessageBox.question(self, "Build wardrobe",
                                f"Create {len(plan)} pieces ({multi} mixing palettes, {printed} with a print):\n\n"
                                f"{lines}\n\nin {ch.wardrobe_dir}?\n\n(Change the settings or the random seed "
                                "for a different selection.)") != QMessageBox.StandardButton.Yes:
            return

        def done(created):
            self._show_character()
            self.tabs.setCurrentIndex(1)
            self.state.characters_changed.emit()
            QMessageBox.information(self, "Wardrobe", f"Added {len(created)} pieces to {ch.name}'s "
                                    "wardrobe and dresser.")
        run_with_progress(self, f"Building {ch.name}'s wardrobe", ch.build_wardrobe, ids,
                          on_done=done, pass_progress=True, plan=plan)

    # ------------------------------------------------------------------ gallery
    def refresh_gallery(self):
        self.gallery.clear()
        ch = self.character
        if not ch:
            return
        cat = self.filter.currentText()
        entries = sorted(ch.data["wardrobe"].values(), key=lambda e: (e["category"], -e["rating"], e["file"]))
        shown = 0
        for e in entries:
            if cat != "All categories" and e["category"] != cat:
                continue
            where = "hamper" if e["id"] in ch.data["hamper"] else "dresser"
            print_ = f" ({e['pattern_name']})" if e.get("pattern_name") else ""
            n_files = len(e.get("files") or [e["file"]])
            self.gallery.add(e["id"], f"{e['item_name']}\n{'+'.join(e['palette_names'])}{print_}",
                             ch.entry_path(e), tooltip=f"{e['category']} — match {e['rating']:.0f}\n"
                                                       f"in {where}\n{e['file']}"
                                                       + (f"\n+{n_files - 1} more image(s)" if n_files > 1 else ""))
            shown += 1
        self.count_label.setText(f"{shown} pieces")

    def _open_editor(self):
        key = self.gallery.current_key()
        if key and self.character:
            self.state.open_in_editor.emit(str(self.character.entry_path(self.character.data["wardrobe"][key])))

    def _remove_entries(self):
        keys = self.gallery.selected_keys()
        if not keys or not self.character:
            return
        r = QMessageBox.question(self, "Remove", f"Remove {len(keys)} piece(s) from the wardrobe and delete "
                                 "their image files?")
        if r == QMessageBox.StandardButton.Yes:
            for k in keys:
                self.character.remove_entry(k, delete_file=True)
            self._show_character()
            self.state.characters_changed.emit()

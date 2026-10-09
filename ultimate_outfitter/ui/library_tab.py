"""Collection inventory: clothing items, colour palettes and patterns."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..core.categories import CATEGORY_NAMES, SLOTS, evaluate_answers, questions_for
from ..core.patterns import PATTERN_QUESTIONS, evaluate_pattern
from ..core.traits import describe
from .color_wheel import PaletteEditorDialog
from .common import IMAGE_FILTER, AppState, Gallery, palette_pixmap, thumb_cache
from .questionnaire import QuestionForm


# ---------------------------------------------------------------------------
# Item questionnaire dialog
# ---------------------------------------------------------------------------


class ItemDialog(QDialog):
    """Ask the category-specific questions for a clothing item.

    ``template`` pre-fills answers (used for editing and for "copy from existing").
    """

    def __init__(self, state: AppState, image_path: str | list[str], template: dict | None = None,
                 parent=None, title: str = "Clothing item"):
        super().__init__(parent)
        self.state = state
        self.image_paths: list[str] = [str(p) for p in (image_path if isinstance(image_path, list) else [image_path])]
        self.setWindowTitle(title)
        self.resize(1000, 800)
        lib = state.library

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        self.images = QListWidget()
        self.images.setViewMode(QListWidget.ViewMode.IconMode)
        self.images.setIconSize(QSize(56, 56))
        self.images.setFixedHeight(84)
        self.images.setFlow(QListWidget.Flow.LeftToRight)
        self.images.setWrapping(False)
        self.images.currentRowChanged.connect(self._show_image)
        b_add_img = QPushButton("Add image…")
        b_add_img.setToolTip("Add another image of the same item (back view, separate parts...). "
                             "Every image is recoloured and printed the same way.")
        b_add_img.clicked.connect(self._add_image)
        b_rem_img = QPushButton("Remove image")
        b_rem_img.clicked.connect(self._remove_image)
        self._refresh_images()
        self.name_edit = QLineEdit(template["name"] if template else Path(self.image_paths[0]).stem)
        self.category = QComboBox()
        self.category.addItems(CATEGORY_NAMES)
        self.copy_combo = QComboBox()
        self.copy_combo.addItem("— copy answers from an existing item —", None)
        for item in sorted(lib.items.values(), key=lambda i: (i["category"], i["name"])):
            self.copy_combo.addItem(QIcon(thumb_cache.get(lib.abspath(item["image"]), 32)),
                                    f"{item['category']}: {item['name']}", item["id"])
        self.notes = QPlainTextEdit(template.get("notes", "") if template else "")
        self.notes.setMaximumHeight(70)
        self.traits_label = QLabel()
        self.traits_label.setWordWrap(True)
        self.form = QuestionForm()
        self.form.changed.connect(self._update_traits)

        left = QVBoxLayout()
        left.addWidget(self.preview)
        left.addWidget(self.images)
        img_row = QHBoxLayout()
        img_row.addWidget(b_add_img)
        img_row.addWidget(b_rem_img)
        left.addLayout(img_row)
        f = QFormLayout()
        f.addRow("Name", self.name_edit)
        f.addRow("Category", self.category)
        left.addLayout(f)
        left.addWidget(self.copy_combo)
        left.addWidget(QLabel("Notes"))
        left.addWidget(self.notes)
        left.addWidget(QLabel("<b>Personalities most likely to favour this item:</b>"))
        left.addWidget(self.traits_label, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(320)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        right = QVBoxLayout()
        right.addWidget(self.form, 1)
        right.addWidget(buttons)
        lay = QHBoxLayout(self)
        lay.addWidget(lw)
        lay.addLayout(right, 1)

        self.category.currentTextChanged.connect(self._category_changed)
        self.copy_combo.currentIndexChanged.connect(self._copy_from)
        if template:
            self.category.setCurrentText(template["category"])
            self._category_changed(template["category"], template.get("answers", {}))
        else:
            self._category_changed(self.category.currentText())

    def _refresh_images(self):
        self.images.clear()
        for p in self.image_paths:
            self.images.addItem(QListWidgetItem(QIcon(thumb_cache.get(p, 56)), ""))
        self.images.setCurrentRow(0)
        self._show_image(0)

    def _show_image(self, row: int):
        if 0 <= row < len(self.image_paths):
            pm = QPixmap(self.image_paths[row])
            if not pm.isNull():
                self.preview.setPixmap(pm.scaled(260, 220, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))

    def _add_image(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add images of this item", "", IMAGE_FILTER)
        if paths:
            self.image_paths += paths
            self._refresh_images()

    def _remove_image(self):
        row = self.images.currentRow()
        if len(self.image_paths) > 1 and 0 <= row < len(self.image_paths):
            del self.image_paths[row]
            self._refresh_images()

    def _category_changed(self, name: str, answers: dict | None = None):
        prev = self.form.answers()
        self.form.set_questions(questions_for(name), answers if answers is not None else prev)
        self._update_traits()

    def _copy_from(self, _idx):
        item_id = self.copy_combo.currentData()
        if not item_id:
            return
        item = self.state.library.items[item_id]
        self.category.blockSignals(True)
        self.category.setCurrentText(item["category"])
        self.category.blockSignals(False)
        self._category_changed(item["category"], item.get("answers", {}))
        if not self.notes.toPlainText():
            self.notes.setPlainText(item.get("notes", ""))
        self.copied_from = item_id

    def _update_traits(self):
        traits, attrs = evaluate_answers(self.category.currentText(), self.form.answers())
        txt = describe(traits, 10) or "(answer the questions)"
        extra = (f"<br><br><i>Slot:</i> {SLOTS.get(attrs['slot'], attrs['slot'])}"
                 f" &nbsp; <i>Warmth:</i> {attrs['warmth']}/5 &nbsp; <i>Formality:</i> {attrs['formality']}/4")
        if attrs.get("activities"):
            extra += "<br><i>Activities:</i> " + ", ".join(attrs["activities"])
        extra += "<br><i>Prints:</i> " + {"none": "never", "primary": "main fabric", "whole": "whole item"}.get(
            attrs.get("print"), "main fabric")
        self.traits_label.setText(txt + extra)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Item", "Please name the item.")
            return
        missing = self.form.unanswered()
        if missing:
            r = QMessageBox.question(self, "Unanswered questions",
                                     f"{len(missing)} question(s) are unanswered:\n- " + "\n- ".join(missing[:8])
                                     + "\n\nSave anyway?")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def result_data(self) -> dict:
        cat = self.category.currentText()
        answers = self.form.answers()
        traits, attrs = evaluate_answers(cat, answers)
        return {"name": self.name_edit.text().strip(), "category": cat, "answers": answers,
                "traits": traits, "attrs": attrs, "notes": self.notes.toPlainText(),
                "copied_from": getattr(self, "copied_from", None), "images": list(self.image_paths)}


# ---------------------------------------------------------------------------
# Items page
# ---------------------------------------------------------------------------


class ItemsPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.filter = QComboBox()
        self.filter.addItem("All categories")
        self.filter.addItems(CATEGORY_NAMES)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.gallery = Gallery(128)
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.detail_img = QLabel()
        self.detail_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_img.setMinimumHeight(260)
        self.detail = QLabel("Select an item")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        b_add = QPushButton("Add item(s)…")
        b_add.setToolTip("One new item per chosen image")
        b_add_multi = QPushButton("Add one item from several images…")
        b_add_multi.setToolTip("e.g. front and back views, or separate parts of one outfit piece")
        b_add_multi.clicked.connect(self.add_multi_image_item)
        b_copy = QPushButton("Copy selected as new item…")
        b_edit = QPushButton("Edit answers…")
        b_editor = QPushButton("Open in image editor")
        b_del = QPushButton("Delete")
        b_add.clicked.connect(self.add_items)
        b_copy.clicked.connect(self.copy_item)
        b_edit.clicked.connect(self.edit_item)
        b_editor.clicked.connect(self.open_editor)
        b_del.clicked.connect(self.delete_items)

        top = QHBoxLayout()
        top.addWidget(self.filter)
        top.addWidget(self.search, 1)
        top.addWidget(b_add)
        top.addWidget(b_add_multi)
        left = QVBoxLayout()
        left.addLayout(top)
        left.addWidget(self.gallery, 1)
        lw = QWidget()
        lw.setLayout(left)
        right = QVBoxLayout()
        right.addWidget(self.detail_img)
        right.addWidget(self.detail, 1)
        for b in (b_copy, b_edit, b_editor, b_del):
            right.addWidget(b)
        rw = QWidget()
        rw.setLayout(right)
        split = QSplitter()
        split.addWidget(lw)
        split.addWidget(rw)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        self.filter.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.gallery.currentItemChanged.connect(self.show_detail)
        self.gallery.itemDoubleClicked.connect(lambda *_: self.edit_item())
        state.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        lib = self.state.library
        cat = self.filter.currentText()
        q = self.search.text().lower()
        current = self.gallery.current_key()
        self.gallery.clear()
        for item in sorted(lib.items.values(), key=lambda i: (i["category"], i["name"].lower())):
            if cat != "All categories" and item["category"] != cat:
                continue
            if q and q not in item["name"].lower() and q not in item["category"].lower():
                continue
            it = self.gallery.add(item["id"], item["name"], lib.abspath(item["image"]),
                                  tooltip=f"{item['category']}\n{describe(item.get('traits', {}), 5)}")
            if item["id"] == current:
                self.gallery.setCurrentItem(it)

    def show_detail(self, *_):
        key = self.gallery.current_key()
        item = self.state.library.items.get(key) if key else None
        if not item:
            self.detail.setText("Select an item")
            self.detail_img.clear()
            return
        self.detail_img.setPixmap(thumb_cache.get(self.state.library.abspath(item["image"]), 256))
        a = item.get("attrs", {})
        src = ""
        if item.get("copied_from") and item["copied_from"] in self.state.library.items:
            src = f"<br><i>Copied from:</i> {self.state.library.items[item['copied_from']]['name']}"
        n_img = len(self.state.library.item_images(item))
        self.detail.setText(
            f"<h3>{item['name']}</h3><i>{item['category']}</i>{src}"
            + (f" &nbsp; ({n_img} images)" if n_img > 1 else "") + "<br><br>"
            f"<b>Favoured by:</b> {describe(item.get('traits', {}), 10)}<br><br>"
            f"<b>Warmth:</b> {a.get('warmth', '?')}/5 &nbsp; <b>Formality:</b> {a.get('formality', '?')}/4<br>"
            f"<b>Activities:</b> {', '.join(a.get('activities', [])) or '-'}<br>"
            f"<b>Notes:</b> {item.get('notes', '')}")

    def add_items(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose clothing item images", "", IMAGE_FILTER)
        for i, path in enumerate(paths):
            dlg = ItemDialog(self.state, path, parent=self,
                             title=f"New clothing item ({i + 1}/{len(paths)})")
            if dlg.exec() != QDialog.DialogCode.Accepted:
                if i < len(paths) - 1 and QMessageBox.question(
                        self, "Add items", "Skip the remaining images too?") == QMessageBox.StandardButton.Yes:
                    break
                continue
            d = dlg.result_data()
            self.state.library.add_item(d["images"], d["name"], d["category"], d["answers"], d["traits"],
                                        d["attrs"], d["notes"], d["copied_from"])
        if paths:
            self.state.library_changed.emit()

    def add_multi_image_item(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose all images of ONE clothing item", "", IMAGE_FILTER)
        if not paths:
            return
        dlg = ItemDialog(self.state, paths, parent=self, title=f"New clothing item ({len(paths)} images)")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data()
            self.state.library.add_item(d["images"], d["name"], d["category"], d["answers"], d["traits"],
                                        d["attrs"], d["notes"], d["copied_from"])
            self.state.library_changed.emit()

    def copy_item(self):
        key = self.gallery.current_key()
        if not key:
            QMessageBox.information(self, "Copy item", "Select the item to copy first.")
            return
        src = self.state.library.items[key]
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Image(s) for the new (near-identical) item - cancel to reuse the same images", "", IMAGE_FILTER)
        if not paths:
            paths = [str(self.state.library.abspath(r)) for r in self.state.library.item_images(src)]
        template = dict(src, name=f"{src['name']} (variant)")
        dlg = ItemDialog(self.state, paths, template, self, "Copy item - adjust what differs")
        dlg.copied_from = key
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data()
            self.state.library.add_item(d["images"], d["name"], d["category"], d["answers"], d["traits"],
                                        d["attrs"], d["notes"], key)
            self.state.library_changed.emit()

    def edit_item(self):
        key = self.gallery.current_key()
        if not key:
            return
        item = self.state.library.items[key]
        lib = self.state.library
        dlg = ItemDialog(self.state, [str(lib.abspath(r)) for r in lib.item_images(item)], item, self, "Edit item")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data()
            d.pop("copied_from", None)
            rels = [lib.import_item_image(p, d["name"]) for p in d.pop("images")]
            self.state.library.update_item(key, image=rels[0], images=rels, **d)
            self.state.library_changed.emit()

    def open_editor(self):
        key = self.gallery.current_key()
        if key:
            self.state.open_in_editor.emit(str(self.state.library.abspath(self.state.library.items[key]["image"])))

    def delete_items(self):
        keys = self.gallery.selected_keys()
        if not keys:
            return
        r = QMessageBox.question(self, "Delete", f"Delete {len(keys)} item(s) from the library?\n"
                                 "(Their image files in the library folder will be removed. "
                                 "Already generated wardrobe images are kept.)")
        if r == QMessageBox.StandardButton.Yes:
            for k in keys:
                self.state.library.remove_item(k, delete_file=True)
            self.state.library_changed.emit()


# ---------------------------------------------------------------------------
# Palettes page
# ---------------------------------------------------------------------------


class PalettesPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.list = QListWidget()
        self.list.setIconSize(palette_pixmap(["#000"], 240, 28).size())
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        b_new = QPushButton("New from colour wheel…")
        b_img = QPushButton("Upload palette image(s)…")
        b_edit = QPushButton("Edit…")
        b_dup = QPushButton("Duplicate")
        b_del = QPushButton("Delete")
        b_new.clicked.connect(self.new_palette)
        b_img.clicked.connect(self.upload)
        b_edit.clicked.connect(self.edit)
        b_dup.clicked.connect(self.duplicate)
        b_del.clicked.connect(self.delete)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit())
        row = QHBoxLayout()
        for b in (b_new, b_img, b_edit, b_dup, b_del):
            row.addWidget(b)
        row.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.list)
        state.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for pal in sorted(self.state.library.palettes.values(), key=lambda p: p["name"].lower()):
            kind = "shades" if pal.get("kind") == "shades" else "varied"
            it = QListWidgetItem(QIcon(palette_pixmap(pal["colors"], 240, 28)),
                                 f"  {pal['name']}  ({len(pal['colors'])} colours, {kind})")
            it.setData(Qt.ItemDataRole.UserRole, pal["id"])
            it.setToolTip(" ".join(pal["colors"]))
            self.list.addItem(it)

    def _current(self):
        it = self.list.currentItem()
        return self.state.library.palettes.get(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def new_palette(self):
        dlg = PaletteEditorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.state.library.add_palette(dlg.name_edit.text().strip(), dlg.colors(), dlg.kind(),
                                           dlg.source_image)
            self.state.library_changed.emit()

    def upload(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose palette images", "", IMAGE_FILTER)
        for path in paths:
            dlg = PaletteEditorDialog(self, name=Path(path).stem)
            dlg.extract_from(path)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.state.library.add_palette(dlg.name_edit.text().strip(), dlg.colors(), dlg.kind(),
                                               dlg.source_image)
        if paths:
            self.state.library_changed.emit()

    def edit(self):
        pal = self._current()
        if not pal:
            return
        src = str(self.state.library.abspath(pal["source"])) if pal.get("source") else None
        dlg = PaletteEditorDialog(self, pal["name"], pal["colors"], pal.get("kind", "varied"), src)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.state.library.update_palette(pal["id"], name=dlg.name_edit.text().strip(),
                                              colors=dlg.colors(), kind=dlg.kind())
            self.state.library_changed.emit()

    def duplicate(self):
        pal = self._current()
        if pal:
            self.state.library.add_palette(pal["name"] + " copy", list(pal["colors"]), pal.get("kind", "varied"))
            self.state.library_changed.emit()

    def delete(self):
        ids = [it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]
        if ids and QMessageBox.question(self, "Delete", f"Delete {len(ids)} palette(s)?") == QMessageBox.StandardButton.Yes:
            for pid in ids:
                self.state.library.remove_palette(pid)
            self.state.library_changed.emit()


# ---------------------------------------------------------------------------
# Patterns page
# ---------------------------------------------------------------------------


class PatternDialog(QDialog):
    """Name, questionnaire and cutaway settings of a pattern."""

    def __init__(self, parent, image_path: str, pattern: dict | None = None, mask_path: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Pattern")
        self.resize(900, 720)
        self.image_path = image_path
        self.mask_path = mask_path
        pattern = pattern or {}
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setPixmap(thumb_cache.get(image_path, 200))
        self.name_edit = QLineEdit(pattern.get("name") or Path(image_path).stem)
        self.cutaway = QComboBox()
        self.cutaway.addItem("No cutaway", "none")
        self.cutaway.addItem("Use the pattern's transparency as cutaway", "alpha")
        self.cutaway.addItem("Use a separate cutaway mask image", "mask")
        self.cutaway.setCurrentIndex(max(0, self.cutaway.findData(pattern.get("cutaway", "none"))))
        self.cutaway.setToolTip("A cutaway makes the garment transparent where the mask is dark / transparent "
                                "(lace, mesh, fishnet, eyelets...).")
        self.mask_label = QLabel()
        self.mask_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_mask = QPushButton("Choose cutaway mask…")
        b_mask.setToolTip("Black = cut away, white = keep. Same size / tiling as the pattern.")
        b_mask.clicked.connect(self._choose_mask)
        if mask_path:
            self.mask_label.setPixmap(thumb_cache.get(mask_path, 120))
        self.traits = QLabel()
        self.traits.setWordWrap(True)
        self.form = QuestionForm(PATTERN_QUESTIONS)
        self.form.changed.connect(self._update)
        if pattern.get("answers"):
            self.form.set_answers(pattern["answers"])
        left = QVBoxLayout()
        left.addWidget(self.preview)
        f = QFormLayout()
        f.addRow("Name", self.name_edit)
        left.addLayout(f)
        left.addWidget(QLabel("<b>Cutaway</b>"))
        left.addWidget(self.cutaway)
        left.addWidget(b_mask)
        left.addWidget(self.mask_label)
        left.addWidget(QLabel("<b>Suits personalities:</b>"))
        left.addWidget(self.traits, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(300)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        right = QVBoxLayout()
        right.addWidget(QLabel("Answer these so the wardrobe creator knows when to use this pattern:"))
        right.addWidget(self.form, 1)
        right.addWidget(buttons)
        lay = QHBoxLayout(self)
        lay.addWidget(lw)
        lay.addLayout(right, 1)
        self._update()

    def _choose_mask(self):
        path, _ = QFileDialog.getOpenFileName(self, "Cutaway mask (black = cut away)", "", IMAGE_FILTER)
        if path:
            self.mask_path = path
            self.mask_label.setPixmap(thumb_cache.get(path, 120))
            self.cutaway.setCurrentIndex(self.cutaway.findData("mask"))

    def _update(self):
        traits, attrs = evaluate_pattern(self.form.answers())
        self.traits.setText((describe(traits, 8) or "(answer the questions)")
                            + "<br><br><i>Used on:</i> " + ", ".join(attrs["uses"]))

    def _accept(self):
        if self.cutaway.currentData() == "mask" and not self.mask_path:
            QMessageBox.warning(self, "Pattern", "Choose a cutaway mask image, or pick another cutaway option.")
            return
        self.accept()

    def pattern_data(self) -> dict:
        traits, attrs = evaluate_pattern(self.form.answers())
        return {"name": self.name_edit.text().strip() or Path(self.image_path).stem,
                "answers": self.form.answers(), "traits": traits, "attrs": attrs,
                "cutaway": self.cutaway.currentData()}


class PatternsPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.gallery = Gallery(128)
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        b_add = QPushButton("Upload pattern(s)…")
        b_edit_q = QPushButton("Edit details && cutaway…")
        b_edit = QPushButton("Open in image editor")
        b_del = QPushButton("Delete")
        b_add.clicked.connect(self.upload)
        b_edit_q.clicked.connect(self.edit)
        b_edit.clicked.connect(self.open_editor)
        b_del.clicked.connect(self.delete)
        self.gallery.itemDoubleClicked.connect(lambda *_: self.edit())
        row = QHBoxLayout()
        for b in (b_add, b_edit_q, b_edit, b_del):
            row.addWidget(b)
        row.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(QLabel("Patterns are used by the Image Editor and by automatic wardrobe generation "
                             "(answer their questions so they go on suitable items and characters)."))
        lay.addWidget(self.gallery)
        state.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.gallery.clear()
        lib = self.state.library
        for pat in sorted(lib.patterns.values(), key=lambda p: p["name"].lower()):
            flags = []
            if not pat.get("answers"):
                flags.append("unanswered")
            if pat.get("cutaway", "none") != "none":
                flags.append("cutaway")
            label = pat["name"] + (f"\n({', '.join(flags)})" if flags else "")
            self.gallery.add(pat["id"], label, lib.abspath(pat["image"]),
                             tooltip=describe(pat.get("traits", {}), 5))

    def upload(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose pattern images", "", IMAGE_FILTER)
        for p in paths:
            dlg = PatternDialog(self, p)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                continue
            r = dlg.pattern_data()
            self.state.library.add_pattern(p, r["name"], r["answers"], r["traits"], r["attrs"], r["cutaway"],
                                           dlg.mask_path if r["cutaway"] == "mask" else None)
        if paths:
            self.state.library_changed.emit()

    def edit(self):
        key = self.gallery.current_key()
        if not key:
            return
        lib = self.state.library
        pat = lib.patterns[key]
        mask = str(lib.abspath(pat["cutaway_mask"])) if pat.get("cutaway_mask") else None
        dlg = PatternDialog(self, str(lib.abspath(pat["image"])), pat, mask)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            r = dlg.pattern_data()
            new_mask = dlg.mask_path if dlg.mask_path and dlg.mask_path != mask else None
            lib.update_pattern(key, cutaway_mask_src=new_mask, **r)
            self.state.library_changed.emit()

    def open_editor(self):
        key = self.gallery.current_key()
        if key:
            self.state.open_in_editor.emit(str(self.state.library.abspath(self.state.library.patterns[key]["image"])))

    def delete(self):
        keys = self.gallery.selected_keys()
        if keys and QMessageBox.question(self, "Delete", f"Delete {len(keys)} pattern(s)?") == QMessageBox.StandardButton.Yes:
            for k in keys:
                self.state.library.remove_pattern(k, delete_file=True)
            self.state.library_changed.emit()


class LibraryTab(QTabWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.addTab(ItemsPage(state), "Clothing Items")
        self.addTab(PalettesPage(state), "Colour Palettes")
        self.addTab(PatternsPage(state), "Patterns")

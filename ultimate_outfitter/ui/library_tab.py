"""Collection inventory: clothing items, colour palettes and patterns."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..core.categories import CATEGORY_NAMES, SLOTS, evaluate_answers, questions_for
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

    def __init__(self, state: AppState, image_path: str, template: dict | None = None,
                 parent=None, title: str = "Clothing item"):
        super().__init__(parent)
        self.state = state
        self.image_path = image_path
        self.setWindowTitle(title)
        self.resize(1000, 760)
        lib = state.library

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(image_path)
        if not pm.isNull():
            self.preview.setPixmap(pm.scaled(260, 260, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
        self.name_edit = QLineEdit(template["name"] if template else Path(image_path).stem)
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
                "copied_from": getattr(self, "copied_from", None)}


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
        self.detail.setText(
            f"<h3>{item['name']}</h3><i>{item['category']}</i>{src}<br><br>"
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
            self.state.library.add_item(path, d["name"], d["category"], d["answers"], d["traits"],
                                        d["attrs"], d["notes"], d["copied_from"])
        if paths:
            self.state.library_changed.emit()

    def copy_item(self):
        key = self.gallery.current_key()
        if not key:
            QMessageBox.information(self, "Copy item", "Select the item to copy first.")
            return
        src = self.state.library.items[key]
        path, _ = QFileDialog.getOpenFileName(
            self, "Image for the new (near-identical) item - cancel to reuse the same image", "", IMAGE_FILTER)
        if not path:
            path = str(self.state.library.abspath(src["image"]))
        template = dict(src, name=f"{src['name']} (variant)")
        dlg = ItemDialog(self.state, path, template, self, "Copy item - adjust what differs")
        dlg.copied_from = key
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data()
            self.state.library.add_item(path, d["name"], d["category"], d["answers"], d["traits"],
                                        d["attrs"], d["notes"], key)
            self.state.library_changed.emit()

    def edit_item(self):
        key = self.gallery.current_key()
        if not key:
            return
        item = self.state.library.items[key]
        dlg = ItemDialog(self.state, str(self.state.library.abspath(item["image"])), item, self, "Edit item")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data()
            d.pop("copied_from", None)
            self.state.library.update_item(key, **d)
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


class PatternsPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.gallery = Gallery(128)
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        b_add = QPushButton("Upload pattern(s)…")
        b_ren = QPushButton("Rename…")
        b_edit = QPushButton("Open in image editor")
        b_del = QPushButton("Delete")
        b_add.clicked.connect(self.upload)
        b_ren.clicked.connect(self.rename)
        b_edit.clicked.connect(self.open_editor)
        b_del.clicked.connect(self.delete)
        row = QHBoxLayout()
        for b in (b_add, b_ren, b_edit, b_del):
            row.addWidget(b)
        row.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(QLabel("Patterns can be applied (tiled, scaled, optionally recoloured with a palette) "
                             "to any selection in the Image Editor."))
        lay.addWidget(self.gallery)
        state.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.gallery.clear()
        lib = self.state.library
        for pat in sorted(lib.patterns.values(), key=lambda p: p["name"].lower()):
            self.gallery.add(pat["id"], pat["name"], lib.abspath(pat["image"]))

    def upload(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose pattern images", "", IMAGE_FILTER)
        for p in paths:
            self.state.library.add_pattern(p, Path(p).stem)
        if paths:
            self.state.library_changed.emit()

    def rename(self):
        key = self.gallery.current_key()
        if not key:
            return
        pat = self.state.library.patterns[key]
        name, ok = QInputDialog.getText(self, "Rename pattern", "Name:", text=pat["name"])
        if ok and name.strip():
            pat["name"] = name.strip()
            self.state.library.save()
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

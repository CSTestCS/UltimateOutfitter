"""Character outfit manager: dresser, hamper, daily outfit with approve / reject."""
from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QScrollArea,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..core.categories import ACTIVITIES, SLOTS, WEATHER
from ..core.character import Character, list_characters
from ..core.outfit import (MOODS, REJECT_REASONS, SETTINGS, DayContext, NoOutfitPossible, OutfitSession, buy,
                           do_laundry, edit_outfit, shop_offer)
from .common import AppState, Gallery, array_to_pixmap, thumb_cache


class DayDialog(QDialog):
    def __init__(self, parent, name: str, last: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{name}'s day")
        last = last or {}
        self.activity = QComboBox()
        self.activity.addItems(ACTIVITIES)
        self.mood = QComboBox()
        self.mood.addItems(list(MOODS))
        self.weather = QComboBox()
        self.weather.addItems(WEATHER)
        self.formality = QComboBox()
        self.formality.addItem("Automatic (from activity)", None)
        for i, label in enumerate(["Very casual", "Casual", "Smart casual", "Formal", "Ceremonial"]):
            self.formality.addItem(label, float(i))
        self.setting = QComboBox()
        self.setting.addItems(SETTINGS)
        self.underwear_only = QCheckBox("Limit the outfit to underwear only")
        self.underwear_only.setToolTip("Available in private or beach / pool settings. Underwear and bras "
                                       "can also stand in for swimwear.")
        self.setting.currentTextChanged.connect(
            lambda t: (self.underwear_only.setEnabled(t != "Public"),
                       t == "Public" and self.underwear_only.setChecked(False)))
        self.notes = QLineEdit()
        # every selector starts on a random choice; the user can still change them
        rng = random.Random()
        for combo in (self.activity, self.mood, self.weather, self.setting, self.formality):
            combo.setCurrentIndex(rng.randrange(combo.count()))
        self.underwear_only.setEnabled(self.setting.currentText() != "Public")
        self.underwear_only.setChecked(False)
        f = QFormLayout(self)
        f.addRow(QLabel(f"<b>What is {name} doing today?</b>"))
        f.addRow("Main activity", self.activity)
        f.addRow("Mood", self.mood)
        f.addRow("Weather", self.weather)
        f.addRow("Setting", self.setting)
        f.addRow("", self.underwear_only)
        f.addRow("Dress code", self.formality)
        f.addRow("Notes", self.notes)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        f.addRow(b)

    def context(self) -> DayContext:
        return DayContext(self.activity.currentText(), self.mood.currentText(), self.weather.currentText(),
                          self.formality.currentData(), self.notes.text(), self.setting.currentText(),
                          self.underwear_only.isChecked())


class RejectDialog(QDialog):
    def __init__(self, parent, piece: str):
        super().__init__(parent)
        self.setWindowTitle("Reject piece")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Why is <b>{piece}</b> rejected?"))
        self.group = QButtonGroup(self)
        for i, (key, label) in enumerate(REJECT_REASONS.items()):
            rb = QRadioButton(label)
            rb.setProperty("key", key)
            self.group.addButton(rb)
            lay.addWidget(rb)
            if i == 0:
                rb.setChecked(True)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def reason(self) -> str:
        return self.group.checkedButton().property("key")


class ShopDialog(QDialog):
    """Random new pieces for a slot the wardrobe can't fill: Shop again for another, Buy to create it."""

    def __init__(self, parent, session: OutfitSession, slot: str):
        super().__init__(parent)
        self.session = session
        self.slot = slot
        self.entry: dict | None = None
        self.offer: dict | None = None
        self.cache: dict = {}
        self.rng = random.Random()
        self.setWindowTitle(f"Shop — {SLOTS.get(slot, slot)}")
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(340, 340)
        self.info = QLabel()
        self.info.setWordWrap(True)
        note = QLabel("A random piece that suits today. It doesn't follow the character's wardrobe rules. "
                      "<b>Shop</b> shows another one; <b>Buy</b> creates it and adds it to the wardrobe and outfit.")
        note.setWordWrap(True)
        b_shop = QPushButton("Shop")
        b_shop.clicked.connect(self.next_offer)
        self.b_buy = QPushButton("Buy")
        self.b_buy.setStyleSheet("font-weight:bold; padding:6px 14px;")
        self.b_buy.clicked.connect(self.buy)
        b_cancel = QPushButton("Cancel")
        b_cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(b_shop)
        row.addStretch(1)
        row.addWidget(b_cancel)
        row.addWidget(self.b_buy)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addWidget(self.preview, 1)
        lay.addWidget(self.info)
        lay.addLayout(row)
        self.next_offer()

    def next_offer(self):
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.offer = shop_offer(self.session, self.slot, self.rng)
            if not self.offer:
                self.preview.setText("The collection has no clothing items for this slot.\n"
                                     "Add some in A. Collection (and at least one palette).")
                self.info.clear()
                self.b_buy.setEnabled(False)
                return
            item, pals, pat = self.offer["item"], self.offer["palettes"], self.offer["pattern"]
            try:
                outs = self.session.character.render_piece(item, pals, pat, self.cache)
                self.preview.setPixmap(array_to_pixmap(outs[0]).scaled(
                    340, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except OSError as exc:
                self.preview.setText(f"Preview failed: {exc}")
            self.info.setText(f"<b>{item['name']}</b> ({item['category']})<br>Palettes: "
                              + " + ".join(p["name"] for p in pals)
                              + (f"<br>Print: {pat['name']}" if pat else ""))
            self.b_buy.setEnabled(True)
        finally:
            QApplication.restoreOverrideCursor()

    def buy(self):
        if not self.offer:
            return
        self.entry = buy(self.session.character, self.offer)
        if self.entry:
            self.accept()
        else:
            QMessageBox.warning(self, "Shop", "The piece could not be created (is its image missing?).")


class PickPieceDialog(QDialog):
    """Pick a clean piece from the dresser (optionally limited to one slot)."""

    def __init__(self, parent, character: Character, slot: str | None = None, exclude=(), title="Add a piece"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 520)
        self.character = character
        self.slot = slot
        self.exclude = set(exclude)
        self.gallery = Gallery(96)
        self.gallery.itemDoubleClicked.connect(lambda *_: self.accept())
        self.only_slot = QCheckBox(f"Only “{SLOTS.get(slot, slot)}” pieces" if slot else "")
        self.only_slot.setChecked(bool(slot))
        self.only_slot.setVisible(bool(slot))
        self.only_slot.toggled.connect(self._fill)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Clean pieces in the dresser (worn pieces in the hamper need laundry first):"))
        lay.addWidget(self.only_slot)
        lay.addWidget(self.gallery, 1)
        lay.addWidget(bb)
        self._fill()

    def _fill(self, *_):
        self.gallery.clear()
        w = self.character.data["wardrobe"]
        entries = [w[e] for e in self.character.data["dresser"] if e in w and e not in self.exclude]
        if self.slot and self.only_slot.isChecked():
            entries = [e for e in entries if e["slot"] == self.slot]
        order = {s: i for i, s in enumerate(SLOTS)}
        entries.sort(key=lambda e: (e["slot"] != self.slot, order.get(e["slot"], 99), e["item_name"]))
        for e in entries:
            self.gallery.add(e["id"], e["item_name"], self.character.entry_path(e),
                             tooltip=f"{SLOTS.get(e['slot'], e['slot'])}\n{'+'.join(e['palette_names'])}")

    def chosen(self) -> str | None:
        return self.gallery.current_key()


class EditOutfitDialog(QDialog):
    """Add, remove or replace pieces of a saved outfit."""

    def __init__(self, parent, character: Character, outfit: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Edit outfit — {outfit.get('date', '')}")
        self.resize(560, 480)
        self.character = character
        self.original = [p["entry_id"] for p in outfit.get("pieces", [])]
        self.ids = list(self.original)
        self.list = QListWidget()
        self.list.setIconSize(thumb_cache.get(character.image_path, 56).size())
        b_add = QPushButton("Add piece…")
        b_add.clicked.connect(self._add)
        b_rep = QPushButton("Replace…")
        b_rep.clicked.connect(self._replace)
        b_rem = QPushButton("Remove")
        b_rem.clicked.connect(self._remove)
        side = QVBoxLayout()
        for b in (b_add, b_rep, b_rem):
            side.addWidget(b)
        side.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addLayout(side)
        note = QLabel("Removed pieces stay in the hamper; added pieces come from the dresser and go to the hamper.")
        note.setWordWrap(True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(row, 1)
        lay.addWidget(note)
        lay.addWidget(bb)
        self._fill()

    def _fill(self):
        self.list.clear()
        w = self.character.data["wardrobe"]
        for eid in self.ids:
            e = w.get(eid)
            if not e:
                continue
            it = QListWidgetItem(QIcon(thumb_cache.get(self.character.entry_path(e), 56)),
                                 f"{SLOTS.get(e['slot'], e['slot'])}: {e['item_name']} ({'+'.join(e['palette_names'])})")
            it.setData(Qt.ItemDataRole.UserRole, eid)
            self.list.addItem(it)

    def _current(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _add(self):
        dlg = PickPieceDialog(self, self.character, exclude=self.ids)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen():
            self.ids.append(dlg.chosen())
            self._fill()

    def _replace(self):
        eid = self._current()
        if not eid:
            QMessageBox.information(self, "Replace", "Select the piece to replace first.")
            return
        slot = self.character.data["wardrobe"][eid]["slot"]
        dlg = PickPieceDialog(self, self.character, slot, exclude=self.ids, title="Replace with…")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen():
            self.ids[self.ids.index(eid)] = dlg.chosen()
            self._fill()

    def _remove(self):
        eid = self._current()
        if eid:
            self.ids.remove(eid)
            self._fill()

    def changes(self) -> tuple[list[str], list[str]]:
        return ([e for e in self.original if e not in self.ids], [e for e in self.ids if e not in self.original])


class OutfitTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.character: Character | None = None
        self.session: OutfitSession | None = None

        self.char_combo = QComboBox()
        self.char_combo.currentIndexChanged.connect(self._select)
        b_plan = QPushButton("Plan today's outfit…")
        b_plan.setStyleSheet("font-weight:bold; padding:6px 14px;")
        b_plan.clicked.connect(self.plan)
        b_laundry = QPushButton("Do laundry (hamper → dresser)")
        b_laundry.clicked.connect(self.laundry)
        top = QHBoxLayout()
        top.addWidget(QLabel("Character:"))
        top.addWidget(self.char_combo, 1)
        top.addWidget(b_plan)
        top.addWidget(b_laundry)

        # dresser & hamper
        self.dresser = Gallery(72)
        self.hamper = Gallery(72)
        self.dresser_label = QLabel()
        self.hamper_label = QLabel()
        dh = QVBoxLayout()
        dh.addWidget(self.dresser_label)
        dh.addWidget(self.dresser, 2)
        dh.addWidget(self.hamper_label)
        dh.addWidget(self.hamper, 1)
        dhw = QWidget()
        dhw.setLayout(dh)

        # proposal
        self.context_label = QLabel("Press “Plan today's outfit…” to have an outfit picked from the dresser.")
        self.context_label.setWordWrap(True)
        self.rows = QWidget()
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.rows)
        self.b_approve_all = QPushButton("Approve all remaining")
        self.b_approve_all.clicked.connect(self.approve_all)
        self.b_accept = QPushButton("Wear this outfit")
        self.b_accept.setStyleSheet("font-weight:bold; padding:6px 14px;")
        self.b_accept.clicked.connect(self.accept_outfit)
        self.b_reroll = QPushButton("Start over")
        self.b_reroll.clicked.connect(self.reroll)
        self.b_shop = QPushButton("Shop for missing pieces…")
        self.b_shop.setToolTip("The wardrobe has nothing for some essential pieces: shop for new ones")
        self.b_shop.clicked.connect(self.shop_missing)
        br = QHBoxLayout()
        br.addWidget(self.b_reroll)
        br.addWidget(self.b_shop)
        br.addStretch(1)
        br.addWidget(self.b_approve_all)
        br.addWidget(self.b_accept)
        prop = QVBoxLayout()
        prop.addWidget(self.context_label)
        prop.addWidget(scroll, 1)
        prop.addLayout(br)
        propw = QWidget()
        propw.setLayout(prop)

        # current & history
        self.current_img = QLabel()
        self.current_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_text = QLabel()
        self.current_text.setWordWrap(True)
        self.history = QListWidget()
        self.history.currentRowChanged.connect(self._show_history)
        self.displayed_outfit: dict | None = None
        self.b_edit = QPushButton("Edit this outfit…")
        self.b_edit.setToolTip("Add, remove or replace pieces (nothing goes back from the hamper to the dresser)")
        self.b_edit.clicked.connect(self.edit_outfit)
        self.current_title = QLabel("<b>Current outfit</b>")
        cur = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(self.current_title, 1)
        head.addWidget(self.b_edit)
        cur.addLayout(head)
        cur.addWidget(self.current_img)
        cur.addWidget(self.current_text)
        cur.addWidget(QLabel("<b>Outfit history</b>"))
        cur.addWidget(self.history, 1)
        curw = QWidget()
        curw.setLayout(cur)

        self.tabs = QTabWidget()
        self.tabs.addTab(propw, "Today's outfit")
        self.tabs.addTab(curw, "Current outfit && history")
        split = QSplitter()
        split.addWidget(dhw)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)

        state.characters_changed.connect(self.refresh_characters)
        state.library_changed.connect(self.refresh_characters)
        state.outfit_changed.connect(self._outfit_changed)
        self.refresh_characters()
        self._render_proposal()

    # --------------------------------------------------------------- characters
    def refresh_characters(self):
        cur = self.char_combo.currentData()
        self.char_combo.blockSignals(True)
        self.char_combo.clear()
        for ch in list_characters(self.state.library):
            self.char_combo.addItem(ch.name, str(ch.path))
        idx = self.char_combo.findData(cur)
        self.char_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.char_combo.blockSignals(False)
        self._select(keep_session=self.char_combo.currentData() == cur)

    def _select(self, *_, keep_session: bool = False):
        path = self.char_combo.currentData()
        if not path:
            self.character = None
        else:
            from pathlib import Path
            self.character = Character.open(self.state.library, Path(path))
        if not keep_session:
            self.session = None
            self._render_proposal()
        elif self.session and self.character:
            self.session.character = self.character
        self.refresh_lists()

    def refresh_lists(self):
        self.dresser.clear()
        self.hamper.clear()
        ch = self.character
        if not ch:
            self.dresser_label.setText("Dresser")
            self.hamper_label.setText("Hamper")
            self.current_text.setText("")
            self.current_img.clear()
            self.history.clear()
            return
        w = ch.data["wardrobe"]
        for gallery, key in ((self.dresser, "dresser"), (self.hamper, "hamper")):
            for eid in ch.data[key]:
                e = w.get(eid)
                if e:
                    gallery.add(eid, e["item_name"], ch.entry_path(e),
                                tooltip=f"{e['category']}\n{'+'.join(e['palette_names'])}")
        self.dresser_label.setText(f"<b>Dresser</b> ({self.dresser.count()} clean pieces)")
        self.hamper_label.setText(f"<b>Hamper</b> ({self.hamper.count()} worn pieces)")
        self.history.blockSignals(True)
        self.history.clear()
        for o in reversed(ch.data.get("outfit_history", [])):
            c = o.get("context", {})
            self.history.addItem(f"{o['date']} — {c.get('activity', '')}, {c.get('mood', '')}, "
                                 f"{c.get('weather', '')} ({len(o['pieces'])} pieces)")
        self.history.blockSignals(False)
        self._show_outfit(ch.data.get("current_outfit"))

    def _show_outfit(self, outfit):
        self.displayed_outfit = outfit
        self.b_edit.setEnabled(bool(outfit))
        is_current = bool(outfit and self.character and outfit is self.character.data.get("current_outfit"))
        self.current_title.setText("<b>Current outfit</b>" if is_current or not outfit else "<b>Past outfit</b>")
        if not outfit:
            self.current_img.clear()
            self.current_text.setText("No outfit yet.")
            return
        if outfit.get("preview"):
            self.current_img.setPixmap(thumb_cache.get(self.character.dir / outfit["preview"], 420))
        else:
            self.current_img.clear()
        c = outfit.get("context", {})
        lines = [f"<b>{outfit['date']}</b> — {c.get('activity')}, mood {c.get('mood')}, {c.get('weather')}"]
        for p in outfit["pieces"]:
            lines.append(f"• {SLOTS.get(p['slot'], p['slot'])}: {p['name']} ({'+'.join(p['palettes'])})")
        self.current_text.setText("<br>".join(lines))

    def edit_outfit(self):
        ch, outfit = self.character, self.displayed_outfit
        if not ch or not outfit:
            return
        dlg = EditOutfitDialog(self, ch, outfit)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        remove, add = dlg.changes()
        if not remove and not add:
            return
        edit_outfit(ch, outfit, remove, add)
        self.state.outfit_changed.emit()   # refreshes the dresser / hamper here and the Interact tab

    def _outfit_changed(self):
        shown = self.displayed_outfit
        row = self.history.currentRow()
        self.refresh_lists()
        if row >= 0:
            self.history.blockSignals(True)
            self.history.setCurrentRow(row)
            self.history.blockSignals(False)
        if shown is not None and self.character and (shown is self.character.data.get("current_outfit")
                                                     or shown in self.character.data["outfit_history"]):
            self._show_outfit(shown)

    def _show_history(self, row):
        hist = self.character.data.get("outfit_history", []) if self.character else []
        if 0 <= row < len(hist):
            self._show_outfit(hist[len(hist) - 1 - row])

    # ------------------------------------------------------------------ planning
    def plan(self):
        ch = self.character
        if not ch:
            QMessageBox.information(self, "Outfit", "Create a character in the Wardrobe Creator first.")
            return
        if not ch.data["wardrobe"]:
            QMessageBox.information(self, "Outfit", f"{ch.name}'s wardrobe is empty. Build it first.")
            return
        last = (ch.data.get("current_outfit") or {}).get("context")
        dlg = DayDialog(self, ch.name, last)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ctx = dlg.context()
        # the Interact tab follows the new day: take over the answers and start a fresh chat
        old_state = ch.data.get("state", {})
        ch.data["state"] = {"mood": ctx.mood, "activity": ctx.activity, "setting": ctx.setting,
                            "weather": ctx.weather, "affinity": old_state.get("affinity", 0.0)}
        ch.data["chat_log"] = []
        ch.save()
        self.session = OutfitSession(ch, ctx)
        self._build()
        self.state.characters_changed.emit()

    def _build(self, allow_incomplete: bool = False):
        try:
            self.session.build(allow_incomplete)
        except NoOutfitPossible as exc:
            msg = f"No complete outfit can be made from the dresser.\nMissing: {', '.join(exc.missing)}"
            if exc.laundry_helps and not allow_incomplete:
                box = QMessageBox(QMessageBox.Icon.Question, "Laundry needed",
                                  msg + "\n\nRequest laundry to return all worn items from the hamper to the "
                                  "dresser, or wear what is available now?", parent=self)
                b_laundry = box.addButton("Do laundry", QMessageBox.ButtonRole.AcceptRole)
                b_partial = box.addButton("Wear what's available", QMessageBox.ButtonRole.ActionRole)
                b_shop = box.addButton("Shop", QMessageBox.ButtonRole.ActionRole) if exc.shop_slots else None
                box.addButton(QMessageBox.StandardButton.Cancel)
                box.exec()
                if b_shop is not None and box.clickedButton() is b_shop:
                    if self._shop_slots(exc.shop_slots):
                        self._build()
                        return
                if box.clickedButton() is b_laundry:
                    do_laundry(self.session.character)
                    self.state.characters_changed.emit()
                    self._build()
                    return
                if box.clickedButton() is b_partial:
                    self._build(allow_incomplete=True)
                    return
            elif exc.shop_slots:
                r = QMessageBox.question(self, "Outfit", f"{self.session.character.name} has nothing to wear "
                                         "for this right now.\n" + msg + "\n\nGo shopping for the missing pieces?")
                if r == QMessageBox.StandardButton.Yes and self._shop_slots(exc.shop_slots):
                    self._build(allow_incomplete=True)
                    return
            else:
                QMessageBox.warning(self, "Outfit", f"{self.session.character.name} has nothing to wear "
                                    "for this right now.\n" + msg)
            self.session = None
        self._render_proposal()

    def reroll(self):
        if self.session:
            ctx = self.session.context
            self.session = OutfitSession(self.character, ctx)
            self._build()

    def _render_proposal(self):
        while self.rows_layout.count() > 1:
            w = self.rows_layout.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        s = self.session
        self.b_accept.setEnabled(bool(s and s.all_approved()))
        self.b_approve_all.setEnabled(bool(s and s.pending()))
        self.b_reroll.setEnabled(bool(s))
        self.b_shop.setVisible(bool(s and s.shop_slots))
        if not s:
            self.context_label.setText("Press “Plan today's outfit…” to have an outfit picked from the dresser.")
            return
        c = s.context
        txt = f"<b>{s.character.name}</b> — {c.activity}, feeling {c.mood.lower()}, weather: {c.weather.lower()}."
        txt += f" Setting: {c.setting.lower()}" + (" — underwear only." if c.is_underwear_only() else ".")
        if s.warnings:
            txt += "<br><i>" + "<br>".join(s.warnings) + "</i>"
        n_pending = len(s.pending())
        txt += f"<br>{n_pending} piece(s) waiting for approval." if n_pending else "<br>All pieces approved."
        self.context_label.setText(txt)
        w = s.wardrobe
        i = 0
        for slot in SLOTS:
            for eid in s.proposal.get(slot, []):
                e = w[eid]
                self.rows_layout.insertWidget(i, self._row(slot, e, eid in s.approved))
                i += 1

    def _row(self, slot: str, entry: dict, approved: bool) -> QWidget:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.StyledPanel)
        if approved:
            f.setStyleSheet("QFrame { background: rgba(60, 170, 90, 50); }")
        g = QGridLayout(f)
        img = QLabel()
        img.setPixmap(thumb_cache.get(self.session.character.entry_path(entry), 96))
        img.setFixedSize(100, 100)
        g.addWidget(img, 0, 0, 2, 1)
        g.addWidget(QLabel(f"<b>{SLOTS.get(slot, slot)}</b>: {entry['item_name']}"), 0, 1)
        g.addWidget(QLabel(f"{entry['category']} — palettes: {', '.join(entry['palette_names'])}"
                           + ("   ✔ approved" if approved else "")), 1, 1)
        b_ok = QPushButton("Approve")
        b_ok.setEnabled(not approved)
        b_no = QPushButton("Reject…")
        b_ok.clicked.connect(lambda: self._approve(entry["id"]))
        b_no.clicked.connect(lambda: self._reject(entry["id"]))
        g.addWidget(b_ok, 0, 2)
        g.addWidget(b_no, 1, 2)
        g.setColumnStretch(1, 1)
        return f

    def _approve(self, eid):
        self.session.approve(eid)
        self._render_proposal()

    def approve_all(self):
        for eid in self.session.pending():
            self.session.approve(eid)
        self._render_proposal()

    def _reject(self, eid):
        entry = self.session.wardrobe[eid]
        dlg = RejectDialog(self, entry["item_name"])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        reason = dlg.reason()
        slot = self.session.slot_of(eid)
        new = self.session.reject(eid, reason)
        if new is None and reason != "unnecessary":
            box = QMessageBox(QMessageBox.Icon.Question, "No alternative",
                              f"There is nothing else suitable for “{SLOTS.get(slot, slot)}” in the dresser.\n"
                              "Do laundry to return worn items to the dresser, shop for a new piece, "
                              "or leave this slot empty?", parent=self)
            b_laundry = box.addButton("Do laundry", QMessageBox.ButtonRole.AcceptRole)
            b_shop = box.addButton("Shop", QMessageBox.ButtonRole.ActionRole)
            box.addButton("Leave empty", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is b_laundry:
                do_laundry(self.session.character)
                cands = self.session.candidates(slot)
                if cands:
                    self.session.proposal.setdefault(slot, []).append(cands[0][1]["id"])
                self.state.characters_changed.emit()
            elif box.clickedButton() is b_shop:
                self._shop_slots([slot])
        self._render_proposal()

    def _shop_slots(self, slots: list[str]) -> bool:
        """Open the shop for each slot in turn. Returns True if anything was bought."""
        bought = False
        for slot in list(dict.fromkeys(slots)):
            dlg = ShopDialog(self, self.session, slot)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.entry:
                if self.session.proposal:     # an outfit is being put together: wear it right away
                    self.session.add_bought(slot, dlg.entry["id"])
                bought = True
        if bought:
            self.refresh_lists()
            self.state.characters_changed.emit()
        return bought

    def shop_missing(self):
        if self.session and self.session.shop_slots:
            self._shop_slots(self.session.shop_slots)
            self._render_proposal()

    def accept_outfit(self):
        s = self.session
        if not s or not s.all_approved():
            return
        outfit = s.finalize()
        self.session = None
        self.refresh_lists()
        self._render_proposal()
        self.tabs.setCurrentIndex(1)
        self.state.characters_changed.emit()
        QMessageBox.information(self, "Outfit saved", f"Saved as {s.character.name}'s current outfit "
                                f"({len(outfit['pieces'])} pieces moved to the hamper).")

    def laundry(self):
        if not self.character:
            return
        n = do_laundry(self.character)
        self.state.characters_changed.emit()
        QMessageBox.information(self, "Laundry", f"{n} piece(s) washed and returned to the dresser.")

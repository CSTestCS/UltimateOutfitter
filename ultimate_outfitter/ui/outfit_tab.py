"""Character outfit manager: dresser, hamper, daily outfit with approve / reject."""
from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPushButton, QRadioButton, QScrollArea,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..core.categories import ACTIVITIES, SLOTS, WEATHER
from ..core.character import Character, list_characters
from ..core.outfit import MOODS, REJECT_REASONS, SETTINGS, DayContext, NoOutfitPossible, OutfitSession, do_laundry
from .common import AppState, Gallery, thumb_cache


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
        br = QHBoxLayout()
        br.addWidget(self.b_reroll)
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
        cur = QVBoxLayout()
        cur.addWidget(QLabel("<b>Current outfit</b>"))
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
            self.character = Character(self.state.library, Path(path))
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
        if not outfit:
            self.current_img.clear()
            self.current_text.setText("No outfit yet.")
            return
        if outfit.get("preview"):
            self.current_img.setPixmap(thumb_cache.get(self.character.dir / outfit["preview"], 420))
        c = outfit.get("context", {})
        lines = [f"<b>{outfit['date']}</b> — {c.get('activity')}, mood {c.get('mood')}, {c.get('weather')}"]
        for p in outfit["pieces"]:
            lines.append(f"• {SLOTS.get(p['slot'], p['slot'])}: {p['name']} ({'+'.join(p['palettes'])})")
        self.current_text.setText("<br>".join(lines))

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
        self.session = OutfitSession(ch, dlg.context())
        self._build()

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
                box.addButton(QMessageBox.StandardButton.Cancel)
                box.exec()
                if box.clickedButton() is b_laundry:
                    do_laundry(self.session.character)
                    self.state.characters_changed.emit()
                    self._build()
                    return
                if box.clickedButton() is b_partial:
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
            r = QMessageBox.question(
                self, "No alternative",
                f"There is nothing else suitable for “{SLOTS.get(slot, slot)}” in the dresser.\n"
                "Request laundry to return worn items to the dresser and try again?\n"
                "(No = leave this slot empty)")
            if r == QMessageBox.StandardButton.Yes:
                do_laundry(self.session.character)
                cands = self.session.candidates(slot)
                if cands:
                    self.session.proposal.setdefault(slot, []).append(cands[0][1]["id"])
                self.state.characters_changed.emit()
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

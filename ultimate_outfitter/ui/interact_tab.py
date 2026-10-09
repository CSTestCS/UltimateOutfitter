"""F. Interact: chat with a character about their day, mood and outfit."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ..core.categories import ACTIVITIES, WEATHER
from ..core.character import Character, list_characters
from ..core.interact import Conversation
from ..core.outfit import MOODS, SETTINGS
from .common import AppState, thumb_cache

TALK_BUTTONS = [
    ("Greet", "greet"), ("How are you?", "how_are_you"), ("What are you doing?", "ask_activity"),
    ("What are you wearing?", "ask_outfit"), ("Compliment outfit", "compliment_outfit"),
    ("Tease outfit", "tease_outfit"), ("Compliment them", "compliment_them"),
    ("Favourite colour?", "favorite_color"), ("Tell me about yourself", "about_self"),
    ("Tell a joke", "joke"), ("Flirt", "flirt"), ("Comfort", "comfort"), ("Annoy", "annoy"),
    ("Say goodbye", "goodbye"),
]


class InteractTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.character: Character | None = None
        self.conv: Conversation | None = None

        self.char_combo = QComboBox()
        self.char_combo.currentIndexChanged.connect(self._select)
        self.player = QLineEdit("you")
        self.player.setMaximumWidth(160)
        self.player.setToolTip("What the character calls you")
        self.player.textChanged.connect(lambda t: self.conv and setattr(self.conv, "player", t or "you"))
        top = QHBoxLayout()
        top.addWidget(QLabel("Character:"))
        top.addWidget(self.char_combo, 1)
        top.addWidget(QLabel("Your name:"))
        top.addWidget(self.player)

        # left: outfit image + status
        self.outfit_img = QLabel("No outfit yet")
        self.outfit_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.outfit_img.setMinimumSize(320, 320)
        self.status = QLabel()
        self.status.setWordWrap(True)
        left = QVBoxLayout()
        left.addWidget(self.outfit_img, 1)
        left.addWidget(self.status)
        lw = QWidget()
        lw.setLayout(left)

        # right: chat
        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(False)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Say something… (simple phrases like “I love your outfit!” work best)")
        self.entry.returnPressed.connect(self.send_text)
        b_send = QPushButton("Say")
        b_send.clicked.connect(self.send_text)
        b_init = QPushButton("Let them talk")
        b_init.setToolTip("The character takes the initiative and says something on their own")
        b_init.setStyleSheet("font-weight:bold;")
        b_init.clicked.connect(self.initiative)
        entry_row = QHBoxLayout()
        entry_row.addWidget(self.entry, 1)
        entry_row.addWidget(b_send)
        entry_row.addWidget(b_init)

        talk = QGroupBox("Talk")
        grid = QGridLayout(talk)
        for i, (label, intent) in enumerate(TALK_BUTTONS):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, it=intent, lb=label: self.do(it, lb))
            grid.addWidget(b, i // 4, i % 4)

        suggest = QGroupBox("Suggest / change")
        sf = QFormLayout(suggest)
        self.sug_activity = QComboBox()
        self.sug_activity.addItems(ACTIVITIES)
        self.sug_setting = QComboBox()
        self.sug_setting.addItems(SETTINGS)
        self.sug_mood = QComboBox()
        self.sug_mood.addItems(list(MOODS))
        self.sug_weather = QComboBox()
        self.sug_weather.addItems(WEATHER)
        for combo, intent, label in ((self.sug_activity, "suggest_activity", "Suggest"),
                                     (self.sug_setting, "suggest_setting", "Suggest going"),
                                     (self.sug_mood, "set_mood", "Set mood"),
                                     (self.sug_weather, "set_weather", "Weather changes")):
            row = QHBoxLayout()
            row.addWidget(combo, 1)
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, c=combo, it=intent: self.suggest(it, c.currentText()))
            row.addWidget(b)
            sf.addRow({"suggest_activity": "Activity", "suggest_setting": "Setting",
                       "set_mood": "Mood", "set_weather": "Weather"}[intent], row)
        b_clear = QPushButton("Clear chat")
        b_clear.clicked.connect(self.clear_chat)
        sf.addRow(b_clear)

        right = QVBoxLayout()
        right.addWidget(self.log, 1)
        right.addLayout(entry_row)
        right.addWidget(talk)
        right.addWidget(suggest)
        rw = QWidget()
        rw.setLayout(right)

        split = QSplitter()
        split.addWidget(lw)
        split.addWidget(rw)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)

        state.characters_changed.connect(self.refresh_characters)
        state.library_changed.connect(self.refresh_characters)
        self.refresh_characters()

    # ---------------------------------------------------------------- characters
    def refresh_characters(self):
        cur = self.char_combo.currentData()
        self.char_combo.blockSignals(True)
        self.char_combo.clear()
        for ch in list_characters(self.state.library):
            self.char_combo.addItem(ch.name, str(ch.path))
        idx = self.char_combo.findData(cur)
        self.char_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.char_combo.blockSignals(False)
        self._select()

    def _select(self, *_):
        path = self.char_combo.currentData()
        if not path:
            self.character = None
            self.conv = None
            self.log.clear()
            self.status.setText("Create a character in the Wardrobe Creator first.")
            self.outfit_img.setText("No character")
            return
        self.character = Character(self.state.library, Path(path))
        self.conv = Conversation(self.character, self.player.text() or "you")
        self._show_outfit()
        self._render_log()

    def _show_outfit(self):
        ch = self.character
        outfit = ch.data.get("current_outfit")
        if outfit and outfit.get("preview"):
            self.outfit_img.setPixmap(thumb_cache.get(ch.dir / outfit["preview"], 420))
        else:
            self.outfit_img.setPixmap(thumb_cache.get(ch.image_path, 360))
        self._show_status()

    def _show_status(self):
        st = self.conv.state
        outfit = self.character.data.get("current_outfit") or {}
        pieces = ", ".join(p["name"] for p in outfit.get("pieces", [])) or "no outfit chosen yet"
        issues = [i for i, _ in self.conv.outfit_issues() if i != "nothing"]
        labels = {"underdressed": "underdressed", "cold": "too cold", "hot": "too warm", "formal": "overdressed",
                  "casual": "too casual", "wrong_activity": "wrong for the activity"}
        fit = ", ".join(labels.get(i, i) for i in issues) if issues else "suitable"
        self.status.setText(
            f"<b>{html.escape(self.character.name)}</b> — mood: <b>{st['mood']}</b>, "
            f"activity: <b>{st['activity']}</b>, setting: <b>{st['setting']}</b>, weather: {st['weather']}<br>"
            f"<b>Wearing:</b> {html.escape(pieces)}<br><b>Outfit:</b> {fit}")

    # ------------------------------------------------------------------- chat
    def _render_log(self):
        out = []
        for m in self.character.data.get("chat_log", [])[-150:]:
            text = html.escape(m["text"])
            if m["who"] == "sys":
                out.append(f"<p style='color:#888'><i>{text}</i></p>")
            elif m["who"] == "player":
                out.append(f"<p style='color:#2a6fdb'><b>{html.escape(self.player.text() or 'You')}:</b> {text}</p>")
            else:
                out.append(f"<p><b>{html.escape(self.character.name)}:</b> {text}</p>")
        self.log.setHtml("".join(out))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _after(self, reply):
        if reply.changes:
            bits = [f"{k} → {v}" for k, v in reply.changes.items()]
            self.character.data["chat_log"].append({"t": 0, "who": "sys", "text": "(" + ", ".join(bits) + ")"})
            self.character.save()
        self._show_status()
        self._render_log()

    def do(self, intent: str, label: str):
        if not self.conv:
            return
        self.conv.log_player(label)
        self._after(self.conv.respond(intent))

    def suggest(self, intent: str, value: str):
        if not self.conv:
            return
        key = {"suggest_activity": "activity", "suggest_setting": "setting",
               "set_mood": "mood", "set_weather": "weather"}[intent]
        phrase = {"suggest_activity": f"How about we do something else: {value}?",
                  "suggest_setting": f"Let's go somewhere else: {value}.",
                  "set_mood": f"(mood: {value})", "set_weather": f"(the weather turns {value.lower()})"}[intent]
        self.conv.log_player(phrase)
        self._after(self.conv.respond(intent, **{key: value}))

    def send_text(self):
        text = self.entry.text().strip()
        if not text or not self.conv:
            return
        self.entry.clear()
        self.conv.log_player(text)
        self._after(self.conv.respond(Conversation.intent_from_text(text)))

    def initiative(self):
        if self.conv:
            self._after(self.conv.initiative())

    def clear_chat(self):
        if self.character:
            self.character.data["chat_log"] = []
            self.character.save()
            self._render_log()

"""F. Interact: a 3D view of the character in their outfit, and a chat with them."""
from __future__ import annotations

import html
import random
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core import expressions, material_rules, vrm_match
from ..core.animations import AnimationLibrary
from ..core.categories import ACTIVITIES, WEATHER
from ..core.character import Character, list_characters
from ..core.interact import Conversation
from ..core.outfit import MOODS, SETTINGS
from ..core.storage import safe_name, unique_path
from ..core.viewer_server import ViewerServer
from .common import IMAGE_FILTER, AppState, Worker, thumb_cache
from .viewport3d import Viewport3D
from .wardrobe_tab import open_folder

TALK_BUTTONS = [
    ("Greet", "greet"), ("How are you?", "how_are_you"), ("What are you doing?", "ask_activity"),
    ("What are you wearing?", "ask_outfit"), ("Compliment outfit", "compliment_outfit"),
    ("Tease outfit", "tease_outfit"), ("Compliment them", "compliment_them"),
    ("Favourite colour?", "favorite_color"), ("Tell me about yourself", "about_self"),
    ("Tell a joke", "joke"), ("Flirt", "flirt"), ("Comfort", "comfort"), ("Annoy", "annoy"),
    ("Say goodbye", "goodbye"),
]
TIMES = [("Automatic (clock)", "auto"), ("Dawn", "dawn"), ("Morning", "morning"), ("Day", "day"),
         ("Evening", "evening"), ("Night", "night")]


class InteractTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.character: Character | None = None
        self.conv: Conversation | None = None
        self.loaded_vrm: str | None = None
        self.model_info: dict = {}
        self.rng = random.Random()
        self.server = ViewerServer(state.library.root)
        self.anims = AnimationLibrary(state.library.root / "Animations")

        # ---- top bar
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

        # ---- viewport (3D, or the 2D outfit sheet)
        self.viewport = Viewport3D(self.server)
        self.viewport.event.connect(self._viewer_event)
        self.outfit_img = QLabel("No outfit yet")
        self.outfit_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.viewport)
        self.stack.addWidget(self.outfit_img)
        self.status = QLabel()
        self.status.setWordWrap(True)

        b_vrm = QPushButton("Set VRoid model for this outfit…")
        b_vrm.setToolTip("Load a .vrm exported from VRoid Studio that shows the character in the current outfit")
        b_vrm.clicked.connect(self.choose_vrm)
        b_vrm_clear = QPushButton("Remove model")
        b_vrm_clear.clicked.connect(self.remove_vrm)
        self.show_2d = QCheckBox("Show 2D outfit sheet")
        self.show_2d.toggled.connect(self._update_stack)
        self.time_combo = QComboBox()
        for label, key in TIMES:
            self.time_combo.addItem(label, key)
        self.time_combo.currentIndexChanged.connect(self._view_settings_changed)
        self.bg_combo = QComboBox()
        self.bg_combo.addItem("Sky (time & weather)", "sky")
        self.bg_combo.addItem("Solid colour…", "color")
        self.bg_combo.addItem("Image…", "image")
        self.bg_combo.activated.connect(self._background_chosen)
        self.pose_combo = QComboBox()
        self.pose_combo.currentIndexChanged.connect(self._view_settings_changed)
        self.look_cam = QCheckBox("Eyes follow the camera")
        self.look_cam.setChecked(True)
        self.look_cam.toggled.connect(lambda on: self.viewport.call("setLookAtCamera", on))
        b_frame = QPushButton("Frame")
        b_frame.setToolTip("Reset the camera on the character (F)")
        b_frame.clicked.connect(lambda: self.viewport.call("frame"))
        b_expr = QPushButton("Edit expressions…")
        b_expr.setToolTip("Open this character's expressions.txt (mood → blend shapes)")
        b_expr.clicked.connect(self.edit_expressions)
        b_shapes = QPushButton("List model blend shapes")
        b_shapes.clicked.connect(lambda: self.viewport.call("listExpressions", report="shapes"))
        b_anim_dir = QPushButton("Animations folder")
        b_anim_dir.setToolTip("Put .fbx idles, poses and emotes here (see the README.md inside)")
        b_anim_dir.clicked.connect(lambda: open_folder(self.anims.folder))
        b_anim_reload = QPushButton("Reload animations")
        b_anim_reload.clicked.connect(self.reload_animations)

        view_bar1 = QHBoxLayout()
        for w in (b_vrm, b_vrm_clear, self.show_2d, b_frame):
            view_bar1.addWidget(w)
        view_bar1.addStretch(1)
        view_bar2 = QHBoxLayout()
        view_bar2.addWidget(QLabel("Time:"))
        view_bar2.addWidget(self.time_combo)
        view_bar2.addWidget(QLabel("Background:"))
        view_bar2.addWidget(self.bg_combo)
        view_bar2.addWidget(QLabel("Pose:"))
        view_bar2.addWidget(self.pose_combo, 1)
        view_bar2.addWidget(self.look_cam)
        view_bar3 = QHBoxLayout()
        for w in (b_expr, b_shapes, b_anim_dir, b_anim_reload):
            view_bar3.addWidget(w)
        view_bar3.addStretch(1)
        self.wet_mode = QComboBox()
        self.wet_mode.addItem("Wet look: automatic (rain / swimming)", "auto")
        self.wet_mode.addItem("Wet look: always", "on")
        self.wet_mode.addItem("Wet look: never", "off")
        self.wet_mode.currentIndexChanged.connect(lambda *_: self._apply_wet())
        self.matcap_metal = QCheckBox("Reflection (matcap) textures are metallic")
        self.matcap_metal.setChecked(True)
        self.matcap_metal.setToolTip("VRoid uses matcap / sphere textures for shiny metal; render those parts "
                                     "as reflective metal")
        self.matcap_metal.toggled.connect(lambda *_: self._apply_materials())
        b_mats = QPushButton("Edit materials…")
        b_mats.setToolTip("Open this character's materials.txt (force parts of the model to be metallic, silk, "
                          "thin or thick)")
        b_mats.clicked.connect(self.edit_materials)
        b_mat_list = QPushButton("List model materials")
        b_mat_list.clicked.connect(lambda: self.viewport.call("listMaterials", report="materials"))
        view_bar4 = QHBoxLayout()
        for w in (self.wet_mode, self.matcap_metal, b_mats, b_mat_list):
            view_bar4.addWidget(w)
        view_bar4.addStretch(1)
        left = QVBoxLayout()
        left.addWidget(self.stack, 1)
        left.addLayout(view_bar1)
        left.addLayout(view_bar2)
        left.addLayout(view_bar3)
        left.addLayout(view_bar4)
        left.addWidget(self.status)
        lw = QWidget()
        lw.setLayout(left)

        # ---- chat
        self.log = QTextBrowser()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Say something… (“I love your outfit!”, “let's go to the beach”, “go to bed”)")
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
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([900, 520])
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)

        state.characters_changed.connect(self.refresh_characters)
        state.library_changed.connect(self._library_changed)
        self._fill_poses()
        self.refresh_characters()

    # ------------------------------------------------------------ library
    def _library_changed(self):
        root = self.state.library.root
        if self.server.library_root != root:
            self.server.library_root = root
            self.anims = AnimationLibrary(root / "Animations")
            self._fill_poses()
        self.refresh_characters()

    def reload_animations(self):
        self.anims.rescan()
        self._fill_poses()
        self._apply_idle()
        n = len(self.anims.anims)
        self.status.setText(f"{n} animation(s) found in {self.anims.folder}")

    def _fill_poses(self):
        cur = self.pose_combo.currentData()
        self.pose_combo.blockSignals(True)
        self.pose_combo.clear()
        self.pose_combo.addItem("Automatic (idle for the situation)", "auto")
        self.pose_combo.addItem("None (still)", "none")
        for a in self.anims.poses():
            self.pose_combo.addItem(a.path.stem, str(a.path))
        idx = self.pose_combo.findData(cur)
        self.pose_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.pose_combo.blockSignals(False)

    # ---------------------------------------------------------- characters
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
            self.viewport.call("clearModel")
            self.loaded_vrm = None
            self._update_stack()
            return
        self.character = Character(self.state.library, Path(path))
        self.match_info = ""
        self.conv = Conversation(self.character, self.player.text() or "you")
        self.expr = expressions.load(self.character)
        vs = self.character.data.get("viewer", {})
        self.time_combo.blockSignals(True)
        self.time_combo.setCurrentIndex(max(0, self.time_combo.findData(vs.get("time", "auto"))))
        self.time_combo.blockSignals(False)
        self.bg_combo.setCurrentIndex(max(0, self.bg_combo.findData(vs.get("background", {}).get("mode", "sky"))))
        self._show_outfit()
        self._render_log()
        self._sync_view(reload_model=True)

    # ------------------------------------------------------------- viewer
    def _vrm_rel(self) -> str | None:
        ch = self.character
        if not ch:
            return None
        outfit = ch.data.get("current_outfit") or {}
        return outfit.get("vrm") or ch.data.get("viewer", {}).get("default_vrm")

    def _update_stack(self):
        has_model = bool(self.character and self._vrm_rel()) and self.viewport.available
        self.stack.setCurrentIndex(0 if has_model and not self.show_2d.isChecked() else 1)

    def _sync_view(self, reload_model: bool = False):
        """Push model, lighting, background, expression and idle to the viewer."""
        ch = self.character
        if not ch or not self.viewport.available:
            self._update_stack()
            return
        rel = self._vrm_rel()
        if rel and (reload_model or rel != self.loaded_vrm):
            path = ch.dir / rel
            if path.exists():
                self.loaded_vrm = rel
                self.viewport.call("loadVRM", self.server.lib_url(path), report="vrm")
            else:
                self.status.setText(f"Model file is missing: {path}")
        elif not rel and self.loaded_vrm:
            self.viewport.call("clearModel")
            self.loaded_vrm = None
        self._apply_lighting()
        self._apply_background()
        self._apply_expression()
        self._apply_materials()
        self._update_stack()

    def _apply_lighting(self):
        if self.conv:
            self.viewport.call("setLighting", {"weather": self.conv.state["weather"],
                                               "time": self.time_combo.currentData()})

    def _apply_background(self):
        bg = dict(self.character.data.get("viewer", {}).get("background", {"mode": "sky"})) if self.character else {}
        if bg.get("mode") == "image" and bg.get("path"):
            p = self.state.library.root / bg["path"]
            bg["url"] = self.server.lib_url(p) if p.exists() else ""
        self.viewport.call("setBackground", bg)

    def _apply_materials(self):
        """Metallic / silk detection rules for the loaded model, then the wet look."""
        if not self.character or not self.loaded_vrm:
            return
        self.viewport.call("setMaterialRules", {"overrides": material_rules.load_overrides(self.character),
                                                "matcapAsMetal": self.matcap_metal.isChecked()})
        self._apply_wet()

    def _match_wardrobe(self):
        """Compare the model's textures with the wardrobe images (in the background) and send the
        matched pieces' effects (shine masks, thin fabric) to the viewer."""
        ch, rel = self.character, self.loaded_vrm
        if not ch or not rel:
            return
        path = ch.dir / rel

        def done(matches):
            if self.character is not ch or self.loaded_vrm != rel:
                return  # another model / character was selected meanwhile
            payload = []
            for m in matches:
                shine = []
                for sh in m["shine"]:
                    mask = ch.dir / sh["mask"] if sh.get("mask") else None
                    shine.append({"kind": sh["kind"],
                                  "maskUrl": self.server.lib_url(mask) if mask and mask.exists() else None})
                payload.append(dict(m, shine=shine))
            self.viewport.call("setWardrobeMatches", payload)
            self._apply_wet()
            if matches:
                bits = []
                for m in matches:
                    tags = [s["kind"] for s in m["shine"]] + (["thin"] if m["thin"] else [])
                    bits.append(f"{m['material']} → {m['item_name']}" + (f" ({', '.join(tags)})" if tags else ""))
                self.match_info = "Model textures matched to wardrobe pieces: " + "; ".join(bits)
            else:
                self.match_info = "No model textures matched the wardrobe images."
            self._show_status()

        worker = Worker(vrm_match.match_wardrobe, ch, path)
        worker.finished_ok.connect(done)
        worker.failed.connect(lambda msg: setattr(self, "match_info", f"Texture matching failed: {msg}"))
        self._match_worker = worker  # keep a reference while it runs
        worker.start()

    def _apply_wet(self):
        if not self.conv or not self.loaded_vrm:
            return
        mode = self.wet_mode.currentData()
        wet, strength = material_rules.is_wet(self.conv.state)
        if mode == "on":
            wet, strength = True, max(strength, 1.0)
        elif mode == "off":
            wet = False
        self.viewport.call("setWet", {"on": wet, "strength": strength or 1.0, "thinOpacity": 0.7,
                                      "thin": material_rules.thin_keywords(self.character)})

    def edit_materials(self):
        if not self.character:
            return
        path = material_rules.ensure_config(self.character)
        self._edit_text_file(path, f"{self.character.name} - materials.txt", self._apply_materials)

    def _edit_text_file(self, path, title, on_save):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(760, 620)
        edit = QPlainTextEdit(path.read_text(encoding="utf-8"))
        edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        b_save = QPushButton("Save")
        b_open = QPushButton("Open in text editor")
        b_open.clicked.connect(lambda: open_folder(path))
        row = QHBoxLayout()
        row.addWidget(b_open)
        row.addStretch(1)
        row.addWidget(b_save)
        lay = QVBoxLayout(dlg)
        lay.addWidget(edit)
        lay.addLayout(row)

        def save():
            path.write_text(edit.toPlainText(), encoding="utf-8")
            dlg.accept()
        b_save.clicked.connect(save)
        dlg.exec()
        on_save()

    def _show_materials(self, mats: list):
        if not mats:
            QMessageBox.information(self, "Model materials", "Load a VRoid model first.")
            return
        lines = []
        for m in mats:
            tags = []
            if m.get("effect"):
                tags.append(f"{m['effect'].upper()} ({m.get('why')})")
            if m.get("thin"):
                tags.append("thin" + (" - see-through now" if m.get("seeThrough") else ""))
            if m.get("match"):
                mt = m["match"]
                tags.append(f"wardrobe piece “{mt['item']}”" + (f": {'/'.join(mt['shine'])}" + (" (masked)" if mt.get("masked") else "")
                                                             if mt.get("shine") else ""))
            if m.get("matcap") and not m.get("effect"):
                tags.append("has matcap")
            lines.append(f"{m['name']}" + (f"   <- {', '.join(tags)}" if tags else ""))
        dlg = QDialog(self)
        dlg.setWindowTitle("Model materials")
        dlg.resize(720, 560)
        text = QPlainTextEdit("Material name   <- what the preview does with it\n\n" + "\n".join(lines) +
                              "\n\nChange anything with “Edit materials…”, e.g.  Bra = metallic")
        text.setReadOnly(True)
        QVBoxLayout(dlg).addWidget(text)
        dlg.exec()

    def _apply_expression(self):
        if self.conv:
            self.viewport.call("setExpression", expressions.weights_for(self.expr, self.conv.state["mood"]))

    def _apply_idle(self):
        if not self.conv or not self.loaded_vrm:
            return
        pose = self.pose_combo.currentData()
        if pose == "none":
            self.viewport.call("stopAnimation")
            return
        if pose and pose != "auto":
            self.viewport.call("playAnimation", self.server.lib_url(pose), {"loop": True})
            return
        anim = self.anims.choose_idle(self.conv.state, self.conv.tone(), self.rng)
        if anim:
            self.viewport.call("playAnimation", self.server.lib_url(anim.path), {"loop": True})
        else:
            self.viewport.call("stopAnimation")

    def _play_reply(self, reply):
        """Expression, reaction and emote for a chat reply."""
        if not self.loaded_vrm:
            return
        if reply.changes.keys() & {"activity", "setting", "mood", "weather"}:
            self._apply_idle()
        if "weather" in reply.changes:
            self._apply_lighting()
            self._apply_background()
        if reply.changes.keys() & {"activity", "weather"}:
            self._apply_wet()
        self._apply_expression()
        if reply.reaction:
            w = expressions.weights_for(self.expr, reply.reaction)
            if w:
                self.viewport.call("react", w, 2.8)
        if self.pose_combo.currentData() == "auto":
            anim = self.anims.choose_emote(reply.emote, self.conv.state, reply.tone or self.conv.tone(), self.rng)
            if anim is None and reply.emote != "talk":
                anim = self.anims.choose_emote("talk", self.conv.state, reply.tone or self.conv.tone(), self.rng)
            if anim:
                self.viewport.call("playAnimation", self.server.lib_url(anim.path), {"loop": False})

    def _viewer_event(self, ev: dict):
        if ev.get("event") == "vrm":
            res = ev.get("result") or {}
            if res.get("ok"):
                self.model_info = res.get("expressions") or {}
                self.viewport.call("setLookAtCamera", self.look_cam.isChecked())
                self._apply_materials()
                self._match_wardrobe()
                self._apply_expression()
                self._apply_idle()
            else:
                self.status.setText(f"Could not load the model: {res.get('error')}")
                self.loaded_vrm = None
        elif ev.get("event") == "materials":
            self._show_materials(ev.get("result") or [])
        elif ev.get("event") == "shapes":
            res = ev.get("result") or {}
            self._show_shapes(res)

    def _view_settings_changed(self, *_):
        if not self.character:
            return
        vs = self.character.data.setdefault("viewer", {})
        vs["time"] = self.time_combo.currentData()
        self.character.save()
        self._apply_lighting()
        self._apply_background()
        self._apply_idle()

    def _background_chosen(self, _idx):
        ch = self.character
        if not ch:
            return
        mode = self.bg_combo.currentData()
        vs = ch.data.setdefault("viewer", {})
        bg = {"mode": "sky"}
        if mode == "color":
            old = vs.get("background", {}).get("color", "#404040")
            c = QColorDialog.getColor(QColor(old), self, "Background colour")
            if not c.isValid():
                return
            bg = {"mode": "color", "color": c.name()}
        elif mode == "image":
            path, _ = QFileDialog.getOpenFileName(self, "Background image", "", IMAGE_FILTER)
            if not path:
                return
            folder = self.state.library.root / "Backgrounds"
            folder.mkdir(exist_ok=True)
            dest = unique_path(folder / Path(path).name)
            shutil.copy2(path, dest)
            bg = {"mode": "image", "path": dest.relative_to(self.state.library.root).as_posix()}
        vs["background"] = bg
        ch.save()
        self._apply_background()

    def choose_vrm(self):
        ch = self.character
        if not ch:
            return
        path, _ = QFileDialog.getOpenFileName(self, "VRoid model for the current outfit", "", "VRM model (*.vrm)")
        if not path:
            return
        folder = ch.dir / "Models"
        folder.mkdir(exist_ok=True)
        dest = unique_path(folder / f"{safe_name(Path(path).stem)}.vrm")
        shutil.copy2(path, dest)
        rel = dest.relative_to(ch.dir).as_posix()
        outfit = ch.data.get("current_outfit")
        if outfit:
            outfit["vrm"] = rel
            for h in reversed(ch.data.get("outfit_history", [])):
                if h.get("date") == outfit.get("date"):
                    h["vrm"] = rel
                    break
        vs = ch.data.setdefault("viewer", {})
        vs["default_vrm"] = rel  # used for outfits without a model of their own
        ch.save()
        self.show_2d.setChecked(False)
        self._sync_view(reload_model=True)

    def remove_vrm(self):
        ch = self.character
        if not ch:
            return
        outfit = ch.data.get("current_outfit") or {}
        outfit.pop("vrm", None)
        ch.data.get("viewer", {}).pop("default_vrm", None)
        ch.save()
        self._sync_view()

    def edit_expressions(self):
        if not self.character:
            return
        path = expressions.ensure_config(self.character)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{self.character.name} - expressions.txt")
        dlg.resize(760, 620)
        edit = QPlainTextEdit(path.read_text(encoding="utf-8"))
        edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        b_save = QPushButton("Save")
        b_open = QPushButton("Open in text editor")
        b_open.clicked.connect(lambda: open_folder(path))
        row = QHBoxLayout()
        row.addWidget(b_open)
        row.addStretch(1)
        row.addWidget(b_save)
        lay = QVBoxLayout(dlg)
        lay.addWidget(edit)
        lay.addLayout(row)

        def save():
            path.write_text(edit.toPlainText(), encoding="utf-8")
            self.expr = expressions.load(self.character)
            self._apply_expression()
            dlg.accept()
        b_save.clicked.connect(save)
        dlg.exec()
        self.expr = expressions.load(self.character)
        self._apply_expression()

    def _show_shapes(self, res: dict):
        exps = res.get("expressions") or []
        morphs = res.get("morphs") or []
        if not exps and not morphs:
            QMessageBox.information(self, "Blend shapes", "Load a VRoid model first.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Model blend shapes")
        dlg.resize(520, 600)
        text = QPlainTextEdit("VRM expressions:\n  " + "\n  ".join(exps) +
                              "\n\nRaw blend shapes (morph targets):\n  " + "\n  ".join(sorted(morphs)))
        text.setReadOnly(True)
        QVBoxLayout(dlg).addWidget(text)
        dlg.exec()

    # ------------------------------------------------------------- status
    def _show_outfit(self):
        ch = self.character
        outfit = ch.data.get("current_outfit")
        if outfit and outfit.get("preview"):
            self.outfit_img.setPixmap(thumb_cache.get(ch.dir / outfit["preview"], 520))
        else:
            self.outfit_img.setPixmap(thumb_cache.get(ch.image_path, 480))
        self._show_status()

    def _show_status(self):
        st = self.conv.state
        outfit = self.character.data.get("current_outfit") or {}
        pieces = ", ".join(p["name"] for p in outfit.get("pieces", [])) or "no outfit chosen yet"
        issues = [i for i, _ in self.conv.outfit_issues() if i != "nothing"]
        labels = {"underdressed": "underdressed", "cold": "too cold", "hot": "too warm", "formal": "overdressed",
                  "casual": "too casual", "wrong_activity": "wrong for the activity"}
        fit = ", ".join(labels.get(i, i) for i in issues) if issues else "suitable"
        model = "" if self._vrm_rel() else " &nbsp; <i>(no 3D model for this outfit - use “Set VRoid model…”)</i>"
        self.status.setText(
            f"<b>{html.escape(self.character.name)}</b> — mood: <b>{st['mood']}</b>, "
            f"activity: <b>{st['activity']}</b>, setting: <b>{st['setting']}</b>, weather: {st['weather']}<br>"
            f"<b>Wearing:</b> {html.escape(pieces)}<br><b>Outfit:</b> {fit}{model}"
            + (f"<br><i>{html.escape(self.match_info)}</i>" if self._vrm_rel() and getattr(self, "match_info", "") else ""))

    # ---------------------------------------------------------------- chat
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
        self._play_reply(reply)

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
        intent, kwargs = Conversation.parse_text(text)
        self._after(self.conv.respond(intent, **kwargs))

    def initiative(self):
        if self.conv:
            self._after(self.conv.initiative())

    def clear_chat(self):
        if self.character:
            self.character.data["chat_log"] = []
            self.character.save()
            self._render_log()

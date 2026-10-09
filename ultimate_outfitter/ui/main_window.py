"""Main application window."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QTabWidget

from .. import __version__
from ..core.storage import Library, default_data_dir, load_settings, save_settings
from .common import AppState
from .editor_tab import EditorTab
from .interact_tab import InteractTab
from .library_tab import LibraryTab
from .outfit_tab import OutfitTab
from .upscale_tab import UpscaleTab
from .wardrobe_tab import WardrobeTab, open_folder


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        settings = load_settings()
        root = Path(data_dir or settings.get("data_dir") or default_data_dir())
        self.state = AppState(Library(root))
        self.setWindowTitle(f"Ultimate Outfitter {__version__} — {root}")
        self.resize(1400, 900)

        self.tabs = QTabWidget()
        self.library_tab = LibraryTab(self.state)
        self.editor_tab = EditorTab(self.state)
        self.wardrobe_tab = WardrobeTab(self.state)
        self.outfit_tab = OutfitTab(self.state)
        self.upscale_tab = UpscaleTab(self.state)
        self.interact_tab = InteractTab(self.state)
        self.tabs.addTab(self.library_tab, "A. Collection")
        self.tabs.addTab(self.editor_tab, "B. Image Editor")
        self.tabs.addTab(self.wardrobe_tab, "C. Wardrobe Creator")
        self.tabs.addTab(self.outfit_tab, "D. Outfit Manager")
        self.tabs.addTab(self.upscale_tab, "E. Upscaler")
        self.tabs.addTab(self.interact_tab, "F. Interact")
        self.setCentralWidget(self.tabs)
        self.state.open_in_editor.connect(lambda *_: self.tabs.setCurrentWidget(self.editor_tab))
        self.state.open_in_upscaler.connect(lambda *_: self.tabs.setCurrentWidget(self.upscale_tab))

        menu = self.menuBar().addMenu("&File")
        act = QAction("Change library folder…", self)
        act.triggered.connect(self.change_library)
        menu.addAction(act)
        act = QAction("Open library folder", self)
        act.triggered.connect(lambda: open_folder(self.state.library.root))
        menu.addAction(act)
        menu.addSeparator()
        act = QAction("Quit", self)
        act.triggered.connect(self.close)
        menu.addAction(act)
        helpm = self.menuBar().addMenu("&Help")
        act = QAction("About", self)
        act.triggered.connect(self.about)
        helpm.addAction(act)

    def change_library(self):
        path = QFileDialog.getExistingDirectory(self, "Choose library folder", str(self.state.library.root))
        if not path:
            return
        settings = load_settings()
        settings["data_dir"] = path
        save_settings(settings)
        self.state.set_library(Library(path))
        self.setWindowTitle(f"Ultimate Outfitter {__version__} — {path}")

    def about(self):
        QMessageBox.about(self, "Ultimate Outfitter",
                          f"<h3>Ultimate Outfitter {__version__}</h3>"
                          "Collection inventory, image editor, character wardrobe creator, "
                          "outfit manager and texture upscaler.<br><br>"
                          f"Library folder:<br>{self.state.library.root}")

    def closeEvent(self, e):
        if self.editor_tab.dirty and QMessageBox.question(
                self, "Quit", "The image editor has unsaved changes. Quit anyway?") != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        e.accept()


def main(argv=None) -> int:
    import os
    from PySide6.QtCore import QCoreApplication, Qt
    # let the 3D viewport use WebGL on older / blocklisted GPUs, with a software fallback
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--ignore-gpu-blocklist --enable-unsafe-swiftshader")
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    try:  # Qt WebEngine must be imported before the QApplication exists
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        pass
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Ultimate Outfitter")
    app.setStyle("Fusion")
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    icon = base / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    win = MainWindow()
    win.show()
    return app.exec()

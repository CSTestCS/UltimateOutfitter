"""Shared Qt helpers: image conversion, thumbnails, galleries, workers, swatches."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressDialog, QSizePolicy, QWidget)

from ..core.storage import Library

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga *.tif *.tiff)"


class AppState(QObject):
    """Holds the library and broadcasts changes between tabs."""

    library_changed = Signal()
    characters_changed = Signal()
    open_in_editor = Signal(str)      # path
    open_in_upscaler = Signal(str)    # path

    def __init__(self, library: Library):
        super().__init__()
        self.library = library

    def set_library(self, library: Library) -> None:
        self.library = library
        thumb_cache.clear()
        self.library_changed.emit()
        self.characters_changed.emit()


def array_to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr.astype(np.uint8))
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.ascontiguousarray(np.dstack([arr, np.full((h, w), 255, np.uint8)]))
    img = QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
    return img.copy()  # detach from numpy buffer


def array_to_pixmap(arr: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(array_to_qimage(arr))


class _ThumbCache:
    def __init__(self):
        self._cache: dict[tuple[str, int, float], QPixmap] = {}

    def clear(self):
        self._cache.clear()

    def get(self, path: Path | str, size: int = 128) -> QPixmap:
        p = Path(path)
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return placeholder(size)
        key = (str(p), size, mtime)
        if key not in self._cache:
            pm = QPixmap(str(p))
            if pm.isNull():
                pm = placeholder(size)
            else:
                pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._cache[key] = pm
        return self._cache[key]


thumb_cache = _ThumbCache()


def placeholder(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor("#555"))
    return pm


def checker_pixmap(size: int = 16) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor("#cccccc"))
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QColor("#999999"))
    p.fillRect(size, size, size, size, QColor("#999999"))
    p.end()
    return pm


def palette_pixmap(colors: Sequence[str], width: int = 160, height: int = 24) -> QPixmap:
    pm = QPixmap(width, height)
    pm.fill(Qt.GlobalColor.transparent)
    if not colors:
        return pm
    p = QPainter(pm)
    w = width / len(colors)
    for i, c in enumerate(colors):
        p.fillRect(int(i * w), 0, int((i + 1) * w) - int(i * w), height, QColor(c))
    p.end()
    return pm


class Gallery(QListWidget):
    """Icon-mode list of images; each entry carries an id in UserRole."""

    def __init__(self, icon_size: int = 128, parent: QWidget | None = None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setGridSize(QSize(icon_size + 28, icon_size + 44))
        self.setWordWrap(True)
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.icon_size = icon_size

    def add(self, key: str, label: str, path: Path | str | None = None,
            pixmap: QPixmap | None = None, tooltip: str = "") -> QListWidgetItem:
        if pixmap is None:
            pixmap = thumb_cache.get(path, self.icon_size) if path else placeholder(self.icon_size)
        it = QListWidgetItem(QIcon(pixmap), label)
        it.setData(Qt.ItemDataRole.UserRole, key)
        if tooltip:
            it.setToolTip(tooltip)
        self.addItem(it)
        return it

    def selected_keys(self) -> list[str]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.selectedItems()]

    def current_key(self) -> str | None:
        it = self.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


class SwatchRow(QWidget):
    """A row of clickable colour swatches."""

    clicked = Signal(str)

    def __init__(self, colors: Sequence[str] = (), size: int = 22, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self.size = size
        self.set_colors(colors)

    def set_colors(self, colors: Sequence[str]) -> None:
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for c in colors:
            lab = _Swatch(c, self.size)
            lab.clicked.connect(self.clicked.emit)
            self._layout.addWidget(lab)
        self._layout.addStretch(1)


class _Swatch(QLabel):
    clicked = Signal(str)

    def __init__(self, color: str, size: int):
        super().__init__()
        self.color = color
        self.setFixedSize(size, size)
        self.setStyleSheet(f"background:{color}; border:1px solid #222;")
        self.setToolTip(color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, e):
        self.clicked.emit(self.color)


# ---------------------------------------------------------------------------
# background work
# ---------------------------------------------------------------------------


class Worker(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.cancelled = False

    def report(self, done: int, total: int, msg: str = "") -> bool:
        self.progress.emit(done, total, msg)
        return not self.cancelled

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            import traceback
            traceback.print_exc()
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(result)


def run_with_progress(parent: QWidget, title: str, fn: Callable[..., Any], *args,
                      on_done: Callable[[Any], None] | None = None, pass_progress: bool = False,
                      **kwargs) -> Worker:
    """Run ``fn`` in a thread with a modal progress dialog.

    If ``pass_progress`` is true, ``fn`` receives ``progress=worker.report``.
    """
    dlg = QProgressDialog(title, "Cancel", 0, 0, parent)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setMinimumDuration(200)
    dlg.setMinimumWidth(420)
    worker = Worker(fn, *args, **kwargs)
    if pass_progress:
        worker.kwargs["progress"] = worker.report

    def on_progress(done, total, msg):
        dlg.setMaximum(max(total, 1))
        dlg.setValue(done)
        if msg:
            dlg.setLabelText(f"{title}\n{msg}")

    def on_ok(result):
        dlg.close()
        if on_done:
            on_done(result)

    def on_fail(msg):
        dlg.close()
        QMessageBox.critical(parent, title, msg)

    def on_cancel():
        worker.cancelled = True

    worker.progress.connect(on_progress)
    worker.finished_ok.connect(on_ok)
    worker.failed.connect(on_fail)
    dlg.canceled.connect(on_cancel)
    parent._workers = getattr(parent, "_workers", []) + [worker]  # keep reference alive
    worker.finished.connect(lambda: parent._workers.remove(worker) if worker in parent._workers else None)
    worker.start()
    return worker


def busy(fn):
    """Decorator: show a wait cursor while ``fn`` runs."""
    def wrapper(*a, **kw):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn(*a, **kw)
        finally:
            QApplication.restoreOverrideCursor()
    wrapper.__name__ = fn.__name__
    return wrapper

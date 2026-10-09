"""Embedded 3D viewport (QtWebEngine + three.js / three-vrm, see viewer_src/)."""
from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..core.viewer_server import ViewerServer

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAVE_WEBENGINE = True
except ImportError:  # pragma: no cover - depends on the installed Qt modules
    HAVE_WEBENGINE = False


if HAVE_WEBENGINE:
    class _Page(QWebEnginePage):
        message = Signal(dict)

        def javaScriptConsoleMessage(self, level, text, line, source):  # noqa: N802 - Qt override
            if text.startswith("UO:"):
                try:
                    self.message.emit(json.loads(text[3:]))
                except ValueError:
                    pass
            elif level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                print(f"[viewer] {text} ({source}:{line})")


class Viewport3D(QWidget):
    """Thin Python wrapper around ``window.UO`` in the viewer page.

    Calls made before the page has loaded are queued. Asynchronous JS results are reported
    through ``event`` (e.g. {"event": "vrm", "result": {...}}).
    """

    event = Signal(dict)

    def __init__(self, server: ViewerServer, parent=None):
        super().__init__(parent)
        self.server = server
        self.ready = False
        self._queue: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if not HAVE_WEBENGINE:
            msg = QLabel("The 3D viewport needs Qt WebEngine (PySide6-Addons), which isn't installed.")
            msg.setWordWrap(True)
            lay.addWidget(msg)
            self.view = None
            return
        self.view = QWebEngineView(self)
        page = _Page(self.view)
        page.message.connect(self.event.emit)
        self.view.setPage(page)
        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        self.view.loadFinished.connect(self._loaded)
        self.view.load(QUrl(server.viewer_url()))
        lay.addWidget(self.view)

    @property
    def available(self) -> bool:
        return self.view is not None

    def _loaded(self, ok: bool):
        self.ready = ok
        if ok:
            queued, self._queue = self._queue, []
            for code in queued:
                self.view.page().runJavaScript(code)

    def js(self, code: str, callback: Callable[[Any], None] | None = None) -> None:
        if not self.view:
            return
        if not self.ready:
            self._queue.append(code)
            return
        if callback:
            self.view.page().runJavaScript(code, 0, callback)
        else:
            self.view.page().runJavaScript(code)

    def call(self, fn: str, *args: Any, report: str | None = None) -> None:
        """Call ``UO.<fn>(*args)``; with ``report`` the (async) result comes back via ``event``."""
        arg_s = ", ".join(json.dumps(a) for a in args)
        if report:
            code = (f"Promise.resolve(window.UO && UO.{fn}({arg_s})).then(r => console.log('UO:' + "
                    f"JSON.stringify({{event: {json.dumps(report)}, result: r}})))")
        else:
            code = f"window.UO && UO.{fn}({arg_s});"
        self.js(code)

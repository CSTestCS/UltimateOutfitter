"""Tiny local HTTP server for the 3D viewport.

The embedded browser loads the viewer page and the user's VRM / FBX / background files
over http://127.0.0.1:<port>/ instead of file:// URLs (which browsers restrict).
Only two roots are served, both read-only:

    /viewer/<path>   the bundled viewer (assets/viewer)
    /lib/<path>      files inside the current library folder
"""
from __future__ import annotations

import mimetypes
import sys
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


def assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets"


mimetypes.add_type("model/gltf-binary", ".vrm")
mimetypes.add_type("application/octet-stream", ".fbx")
mimetypes.add_type("text/javascript", ".js")


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, server_ref: "ViewerServer", **kwargs):
        self.server_ref = server_ref
        super().__init__(*args, **kwargs)

    def log_message(self, *args):  # keep the console quiet
        pass

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        parts = path.lstrip("/").split("/", 1)
        if len(parts) != 2:
            self.send_error(404)
            return
        root = {"viewer": assets_dir() / "viewer", "lib": self.server_ref.library_root}.get(parts[0])
        if root is None:
            self.send_error(404)
            return
        root = Path(root).resolve()
        target = (root / parts[1]).resolve()
        if root not in target.parents or not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


class ViewerServer:
    def __init__(self, library_root: Path):
        self.library_root = Path(library_root)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, server_ref=self))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def viewer_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/viewer/index.html"

    def lib_url(self, path: Path | str) -> str:
        """URL for a file inside the library folder."""
        rel = Path(path).resolve().relative_to(self.library_root.resolve()).as_posix()
        return f"http://127.0.0.1:{self.port}/lib/{quote(rel)}"

    def stop(self) -> None:
        self.httpd.shutdown()

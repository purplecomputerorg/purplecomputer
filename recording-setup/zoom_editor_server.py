#!/usr/bin/env python3
"""Local HTTP server for the zoom keyframe editor.

Serves the editor UI and provides API endpoints for listing videos,
loading/saving zoom events, and streaming video files with Range support.

Usage:
    python recording-setup/zoom_editor_server.py
    # Opens http://localhost:8000
"""

import json
import os
import re
import webbrowser
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = 8000
BASE_DIR = Path(__file__).parent
RECORDINGS_DIR = BASE_DIR.parent / "recordings"
EVENTS_FILE = RECORDINGS_DIR / "zoom_events.json"


class ZoomEditorHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file(BASE_DIR / "zoom_editor.html", "text/html")
        elif self.path == "/api/videos":
            self._serve_video_list()
        elif self.path == "/api/events":
            self._serve_events()
        elif self.path.startswith("/recordings/"):
            self._serve_recording()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/events":
            self._save_events()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_file(self, path: Path, content_type: str):
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_video_list(self):
        videos = []
        if RECORDINGS_DIR.exists():
            videos = sorted(f.name for f in RECORDINGS_DIR.glob("*.mp4"))
        self._json_response(videos)

    def _serve_events(self):
        if EVENTS_FILE.exists():
            events = json.loads(EVENTS_FILE.read_text())
        else:
            events = []
        self._json_response(events)

    def _save_events(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        events = json.loads(body)
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        EVENTS_FILE.write_text(json.dumps(events, indent=2) + "\n")
        self._json_response({"ok": True})

    def _serve_recording(self):
        # Strip /recordings/ prefix, sanitize
        name = self.path[len("/recordings/"):]
        if "/" in name or ".." in name:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        filepath = RECORDINGS_DIR / name
        if not filepath.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        file_size = filepath.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            # Parse Range: bytes=start-end
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if not m:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(filepath, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(length))
        else:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quiet down range request spam
        if "206" not in str(args):
            super().log_message(format, *args)


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    server = HTTPServer(("", PORT), ZoomEditorHandler)
    url = f"http://localhost:{PORT}"
    print(f"Zoom editor running at {url}")
    print("Press Ctrl+C to stop.\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

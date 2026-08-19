#!/usr/bin/env python3
"""Local review interface for the AI use log.

Serves a single-page UI on 127.0.0.1 for marking task segments against the
rubric, and writes decisions back into queue.json.

This is a LOCAL tool. The queue holds raw prompt text -- clinical material,
file paths, anything typed into a session -- so the server binds to loopback
only, serves two fixed routes, and never touches assets/ or anything the site
publishes. Nothing here is a publishing step.

Usage:
  python3 tools/ai-log/review.py            # http://127.0.0.1:8787
  python3 tools/ai-log/review.py --port 9000
"""

import argparse
import json
import os
import socketserver
import sys
import tempfile
from http.server import BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "queue", "queue.json")
PAGE = os.path.join(HERE, "review.html")

# Only these may be written from the browser. Everything else in a segment is
# derived from transcripts and must survive re-extraction untouched.
WRITABLE = {
    "status": {"pending", "approved", "rejected"},
    "destination": {"", "instrumental", "authored-prose", "mixed"},
    "specification": {"", "tight", "partial", "loose"},
    "discretion": {"", "directed", "discretionary"},
    "stage": {"", "before", "during", "after"},
    "outcome": {"", "accepted", "corrected", "reverted"},
    "summary": None,  # free text
    "notes": None,
}


def load():
    with open(QUEUE, encoding="utf-8") as handle:
        return json.load(handle)


def save(payload):
    """Write atomically -- a half-written archive would lose review work."""
    directory = os.path.dirname(QUEUE)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, QUEUE)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the terminal readable

    def _send(self, code, body, ctype="application/json"):
        blob = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(PAGE, "rb") as handle:
                return self._send(200, handle.read(), "text/html; charset=utf-8")
        if self.path == "/api/queue":
            return self._send(200, json.dumps(load()))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if not self.path.startswith("/api/segment/"):
            return self._send(404, json.dumps({"error": "not found"}))

        seg_id = self.path[len("/api/segment/"):]
        length = int(self.headers.get("Content-Length") or 0)
        try:
            patch = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, json.dumps({"error": "bad json"}))

        clean = {}
        for key, value in patch.items():
            if key not in WRITABLE:
                return self._send(400, json.dumps({"error": "field not writable: %s" % key}))
            allowed = WRITABLE[key]
            if allowed is not None and value not in allowed:
                return self._send(400, json.dumps({"error": "bad value for %s: %r" % (key, value)}))
            clean[key] = value

        payload = load()
        for segment in payload["segments"]:
            if segment["id"] == seg_id:
                segment.update(clean)
                save(payload)
                return self._send(200, json.dumps({"ok": True, "id": seg_id}))
        self._send(404, json.dumps({"error": "no such segment"}))


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    if not os.path.exists(QUEUE):
        print("No queue yet. Run: python3 tools/ai-log/extract.py", file=sys.stderr)
        return 1

    total = len(load()["segments"])
    print("AI use log review -- %d segments" % total)
    print("  http://127.0.0.1:%d" % args.port)
    print("  local only; the queue holds raw prompt text and nothing here publishes")
    print("  ctrl-c to stop")
    with Server(("127.0.0.1", args.port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

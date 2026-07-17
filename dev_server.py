"""Dev-статика Mini App без кэша: ES-модули всегда свежие (Cache-Control: no-store)."""
import http.server
import sys

DIRECTORY = sys.argv[1] if len(sys.argv) > 1 else "miniapp"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5500


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), NoCacheHandler).serve_forever()

"""A tiny local website for tests. It records when each request arrives."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FixtureSite:
    def __init__(self, robots_txt="User-agent: *\nAllow: /\n", responder=None):
        self.robots_txt = robots_txt
        # responder(path, hit_number) -> (status, headers dict, body str), or None for a normal page
        self.responder = responder
        self.hits = []  # (path, monotonic time)
        self.lock = threading.Lock()
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                with site.lock:
                    site.hits.append((self.path, time.monotonic()))
                    hit_number = sum(1 for p, _ in site.hits if p == self.path)
                if self.path == "/robots.txt":
                    status, headers, body = 200, {}, site.robots_txt
                else:
                    result = site.responder(self.path, hit_number) if site.responder else None
                    status, headers, body = result or (200, {}, f"<html><body>{self.path}</body></html>")
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()

    def times_for(self, prefix):
        return [t for p, t in self.hits if p.startswith(prefix)]

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lagebericht.fetch import FetchError, SafeFetcher


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            body = b"<rss />"
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/large":
            body = b"x" * 128
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/foreign":
            self.send_response(302)
            self.send_header("Location", "https://evil.example/steal")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def fetcher(self, max_bytes=2_000_000):
        return SafeFetcher(max_bytes=max_bytes, allow_test_http=True, allow_private_hosts=True)

    def test_fetches_allowlisted_resource(self):
        result = self.fetcher().fetch(self.base + "/ok", frozenset({"127.0.0.1"}))
        self.assertEqual(result.body, b"<rss />")
        self.assertEqual(result.content_type, "application/rss+xml")

    def test_follows_allowlisted_relative_redirect(self):
        result = self.fetcher().fetch(self.base + "/redirect", frozenset({"127.0.0.1"}))
        self.assertTrue(result.final_url.endswith("/ok"))

    def test_rejects_foreign_redirect(self):
        with self.assertRaisesRegex(FetchError, "allowlisted"):
            self.fetcher().fetch(self.base + "/foreign", frozenset({"127.0.0.1"}))

    def test_rejects_oversized_response(self):
        with self.assertRaisesRegex(FetchError, "size limit"):
            self.fetcher(max_bytes=64).fetch(self.base + "/large", frozenset({"127.0.0.1"}))

    def test_rejects_http_in_production(self):
        with self.assertRaisesRegex(FetchError, "https"):
            SafeFetcher().fetch(self.base + "/ok", frozenset({"127.0.0.1"}))


if __name__ == "__main__":
    unittest.main()


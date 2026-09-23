import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from arena import server
from arena.chess_session import ChessSession


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def call(self, path, data=None, token=None, origin=None):
        headers = {}
        if token:
            headers["X-Arena-Token"] = token
        if origin:
            headers["Origin"] = origin
        body = json.dumps(data).encode() if data is not None else None
        try:
            with urllib.request.urlopen(
                urllib.request.Request(self.base + path, body, headers), timeout=5
            ) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_secrets_and_legacy_endpoints_unavailable(self):
        for path in (
            "/.env",
            "/../.env",
            "/arena/providers.py",
            "/runs",
            "/config/local.json",
            "/api/devices",
            "/api/frame",
        ):
            self.assertEqual(self.call(path)[0], 404)

    def test_cross_origin_and_missing_token_rejected(self):
        self.assertEqual(self.call("/api/stop", {})[0], 403)
        self.assertEqual(self.call("/api/stop", {}, server.TOKEN, "https://example.com")[0], 403)

    def test_missing_key_cannot_start_fake_game(self):
        with (
            patch.object(server, "SESSION", ChessSession()),
            patch(
                "arena.chess_session.providers_ready", return_value={"jev": False, "laya": False}
            ),
        ):
            status, body = self.call("/api/start", {}, server.TOKEN)
            self.assertEqual(status, 400)
            self.assertIn("OpenRouter", json.loads(body)["error"])
            self.assertEqual(server.SESSION.data["status"], "idle")

    def test_board_assets_and_pgn(self):
        with patch.object(server, "SESSION", ChessSession()):
            status, body = self.call("/api/state")
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["pieces"]), 32)
            self.assertIn(b"<svg", self.call("/pieces/K.svg")[1])
            self.assertEqual(self.call("/pieces/xx.svg")[0], 404)
            self.assertIn(b'[White "Jev"]', self.call("/api/pgn")[1])


class PackageAssetTests(unittest.TestCase):
    def test_packaged_dashboard_assets_exist(self):
        from importlib.resources import files

        root = files("arena").joinpath("web")
        for name in ("index.html", "app.js", "style.css"):
            with self.subTest(name=name):
                self.assertTrue(root.joinpath(name).read_bytes())

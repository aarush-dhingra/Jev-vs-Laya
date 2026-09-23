"""Local chess spectator server. No emulator or vision endpoints are exposed."""

import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import chess
import chess.svg

from arena.chess_session import ChessSession, providers_ready
from arena.providers import ProviderError

SESSION = ChessSession()
TOKEN = secrets.token_urlsafe(24)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, mime="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        for k, v in [
            ("Content-Type", mime),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            (
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            ),
        ]:
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get("Host") in (
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        )

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {"error": "Local access only"})
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                return self.send(
                    200,
                    {"ok": True, "game": "chess", "token": TOKEN, "providers": providers_ready()},
                )
            if path == "/api/state":
                return self.send(200, SESSION.snapshot())
            if path == "/api/export":
                return self.send(200, SESSION.snapshot())
            if path == "/api/pgn":
                with SESSION.lock:
                    content = SESSION.pgn()
                return self.send(200, content.encode(), "application/x-chess-pgn")
            if path.startswith("/pieces/") and path.endswith(".svg"):
                symbol = path[len("/pieces/") : -4]
                if len(symbol) != 1 or symbol not in "KQRBNPkqrbnp":
                    return self.send(404, {"error": "Unknown piece"})
                return self.send(
                    200,
                    chess.svg.piece(chess.Piece.from_symbol(symbol), size=100).encode(),
                    "image/svg+xml",
                )
            files = {
                "/": "index.html",
                "/index.html": "index.html",
                "/app.js": "app.js",
                "/style.css": "style.css",
            }
            if path not in files:
                return self.send(404, {"error": "Not found"})
            file = Path(__file__).parent / "web" / files[path]
            return self.send(
                200,
                file.read_bytes(),
                mimetypes.guess_type(str(file))[0] or "application/octet-stream",
            )
        except (ValueError, ProviderError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception:
            self.send(500, {"error": "Local chess operation failed."})

    def do_POST(self):
        origin = self.headers.get("Origin")
        if (
            not self.valid_host()
            or self.headers.get("X-Arena-Token") != TOKEN
            or (
                origin
                and origin
                not in (
                    f"http://127.0.0.1:{self.server.server_port}",
                    f"http://localhost:{self.server.server_port}",
                )
            )
        ):
            return self.send(403, {"error": "Refresh this local page before sending commands."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 10000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            if self.path == "/api/start":
                SESSION.start(data)
            elif self.path == "/api/stop":
                SESSION.stop()
            elif self.path == "/api/pause":
                SESSION.pause()
            else:
                return self.send(404, {"error": "Not found"})
            self.send(200, {"ok": True})
        except (ValueError, TypeError, ProviderError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception:
            self.send(500, {"error": "Unable to apply command."})


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    SESSION.restore_latest()
    print(f"Decision Chess | http://127.0.0.1:{args.port}", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        SESSION.stop()


if __name__ == "__main__":
    main()

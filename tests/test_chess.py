import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import chess
import chess.pgn

from arena.chess_session import ChessPolicy, ChessSession
from arena.providers import Budget, ProviderError


def decision():
    return {"source": "test", "model": "fixture", "latency_ms": 1, "stages": []}


class ChessTests(unittest.TestCase):
    def test_special_moves(self):
        fixtures = [
            ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", "f1", "R"),
            ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q", "a8", "Q"),
            ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6", "d6", "P"),
        ]
        for fen, uci, square, symbol in fixtures:
            s = ChessSession()
            s.board = chess.Board(fen)
            s.apply(chess.Move.from_uci(uci), decision())
            self.assertEqual(s.board.piece_at(chess.parse_square(square)).symbol(), symbol)
            if uci == "e5d6":
                self.assertIsNone(s.board.piece_at(chess.D5))
                self.assertEqual(s.data["history"][0]["captured"], "p")
        s = ChessSession()
        with self.assertRaises(ProviderError):
            s.apply(chess.Move.from_uci("e2e5"), decision())
        self.assertEqual(s.data["history"], [])

    def test_endings_and_pgn(self):
        s = ChessSession()
        for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
            s.apply(chess.Move.from_uci(uci), decision())
        self.assertTrue(s.finish_board())
        self.assertEqual(s.data["result"], "0-1")
        game = chess.pgn.read_game(io.StringIO(s.pgn()))
        self.assertFalse(game.errors)
        self.assertEqual(game.end().board().fen(), s.board.fen())
        for fen, termination in [
            ("7k/5K2/6Q1/8/8/8/8/8 b - - 0 1", "stalemate"),
            ("7k/8/8/8/8/8/8/K7 w - - 0 1", "insufficient material"),
            ("7k/8/8/8/8/8/8/KR6 w - - 100 60", "fifty moves"),
        ]:
            s.board = chess.Board(fen)
            self.assertTrue(s.finish_board())
            self.assertEqual(s.data["termination"], termination)
        s.board = chess.Board()
        for move in ("g1f3", "g8f6", "f3g1", "f6g8") * 2:
            s.board.push_uci(move)
        self.assertTrue(s.finish_board())
        self.assertEqual(s.data["termination"], "threefold repetition")

    def test_choices_preserve_all_legal_moves(self):
        board = chess.Board()
        seen = []

        def ask(state, criteria, instruction):
            seen.append(set(criteria))
            return {"choice": "e2" if len(seen) == 1 else "e2e4"}, "fixture"

        policy = ChessPolicy("jev", Budget(4), threading.Event(), mode="unassisted")
        with patch.object(policy, "ask", side_effect=ask):
            move, _ = policy.decide(board)
        self.assertEqual(move.uci(), "e2e4")
        self.assertEqual(seen[0], {chess.square_name(m.from_square) for m in board.legal_moves})
        self.assertEqual(seen[1], {"e2e3", "e2e4"})

    def test_color_swap_and_recording(self):
        def play(policy, board):
            return chess.Move.from_uci(
                ("f2f3", "e7e5", "g2g4", "d8h4")[len(board.move_stack)]
            ), decision()

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("arena.chess_session.ROOT", Path(folder)),
            patch("arena.chess_session.providers_ready", return_value={"jev": True, "laya": True}),
            patch.object(ChessPolicy, "decide", play),
            patch("arena.chess_review.review_game", return_value={"status": "complete"}),
        ):
            s = ChessSession()
            s.start({"games": 2, "delay": 0.25})
            s.thread.join(10)
            self.assertFalse(s.thread.is_alive())
            self.assertEqual(s.data["status"], "finished")
            self.assertEqual(
                [r["policies"] for r in s.data["results"]], [["jev", "laya"], ["laya", "jev"]]
            )
            self.assertTrue((s.run_dir / "game-2.pgn").exists())

    def test_pause_stop_discards_pending_response(self):
        entered = threading.Event()
        release = threading.Event()

        def play(policy, board):
            entered.set()
            release.wait(3)
            return chess.Move.from_uci("e2e4"), decision()

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("arena.chess_session.ROOT", Path(folder)),
            patch("arena.chess_session.providers_ready", return_value={"jev": True, "laya": True}),
            patch.object(ChessPolicy, "decide", play),
            patch("arena.chess_review.review_game", return_value={"status": "complete"}),
        ):
            s = ChessSession()
            s.start({})
            self.assertTrue(entered.wait(2))
            s.pause()
            self.assertEqual(s.data["status"], "paused")
            s.stop()
            release.set()
            s.thread.join(3)
            self.assertEqual(s.data["history"], [])
            self.assertEqual(s.data["status"], "stopped")

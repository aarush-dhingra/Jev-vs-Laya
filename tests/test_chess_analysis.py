import threading
import unittest
from unittest.mock import patch

import chess

from arena.chess_analysis import candidates, facts, prepare
from arena.chess_review import aggregate, review_game
from arena.chess_session import ChessPolicy
from arena.providers import Budget


class LightweightTests(unittest.TestCase):
    def test_mate_in_one_and_no_engine_in_live_path(self):
        board = chess.Board("7k/5K2/6Q1/8/8/8/8/8 w - - 0 1")
        with patch(
            "chess.engine.SimpleEngine.popen_uci",
            side_effect=AssertionError("Stockfish must not run live"),
        ):
            result = prepare(board, Budget(4), threading.Event())
        self.assertFalse(result["stockfish_used"])
        for row in result["candidates"]:
            b = board.copy()
            b.push_uci(row["uci"])
            self.assertTrue(b.is_checkmate())

    def test_finds_opponents_immediate_mate(self):
        b = chess.Board()
        b.push_uci("f2f3")
        b.push_uci("e7e5")
        row = facts(b, chess.Move.from_uci("g2g4"))
        self.assertTrue(row["allows_mate"])
        self.assertEqual(row["reply"], "Qh4#")
        rows, _ = candidates(b)
        self.assertNotIn("g2g4", [r["uci"] for r in rows])

    def test_same_board_same_candidates_and_retains_history(self):
        b = chess.Board()
        b.push_uci("e2e4")
        budget = Budget(4)
        a = prepare(b, budget, threading.Event())
        c = prepare(b, budget, threading.Event())
        self.assertEqual(a, c)
        self.assertEqual(budget.calls, 0)
        self.assertEqual(a["recent_moves"], ["e4"])
        self.assertLessEqual(len(a["candidates"]), 4)
        self.assertTrue(
            all(chess.Move.from_uci(r["uci"]) in b.legal_moves for r in a["candidates"])
        )

    def test_final_choice_has_no_engine_scores(self):
        b = chess.Board()
        seen = []

        def ask(state, criteria, instruction):
            seen.append(criteria)
            return {"choice": next(iter(criteria))}, "fixture"

        for name in ("jev", "laya"):
            p = ChessPolicy(name, Budget(4), threading.Event())
            with patch.object(p, "ask", side_effect=ask):
                move, data = p.decide(b)
            self.assertIn(move, b.legal_moves)
        self.assertEqual(seen[0], seen[1])
        self.assertNotIn("heuristic", str(seen))
        self.assertNotIn("eval ", str(seen))

    def test_review_metrics_without_synthetic_ratings(self):
        rows = [
            {
                "side": 0,
                "loss_cp": 0,
                "played": "e2e4",
                "best": "e2e4",
                "classification": "excellent",
                "missed_mate": False,
                "allowed_mate": False,
            },
            {
                "side": 1,
                "loss_cp": 300,
                "played": "e7e5",
                "best": "c7c5",
                "classification": "blunder",
                "missed_mate": False,
                "allowed_mate": True,
            },
        ]
        white, black = aggregate(rows, ["jev", "laya"])
        self.assertNotIn("accuracy", white)
        self.assertNotIn("grade", white)
        self.assertEqual(white["average_cp_loss"], 0)
        self.assertEqual(black["counts"]["blunder"], 1)
        self.assertEqual(black["average_cp_loss"], 300)
        self.assertIsNone(white["elo"])

    def test_finished_game_review_scores_both_sides(self):
        b = chess.Board()
        for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
            b.push_uci(move)
        progress = []
        report = review_game(
            b, ["jev", "laya"], threading.Event(), lambda done, total: progress.append(done)
        )
        self.assertTrue(all(r["loss_cp"] == 0 for r in report["moves"] if r["played"] == r["best"]))
        self.assertEqual(len(report["moves"]), 4)
        self.assertEqual(progress, [1, 2, 3, 4])
        self.assertEqual([p["moves"] for p in report["players"]], [2, 2])
        self.assertTrue(report["moves"][2]["allowed_mate"])
        self.assertEqual(report["moves"][3]["loss_cp"], 0)

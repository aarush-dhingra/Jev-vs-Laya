"""Post-game-only Stockfish review. Move-level analysis without a synthetic rating."""

import subprocess
from concurrent.futures import CancelledError

import chess
import chess.engine

from .providers import ROOT, ProviderError


def engine_path():
    paths = list((ROOT / "var" / "tools" / "stockfish").rglob("*.exe"))
    if not paths:
        raise ProviderError("Stockfish reviewer missing; run scripts/Install-ChessEngine.ps1.")
    return str(paths[0])


def classify(loss):
    return (
        "excellent"
        if loss <= 20
        else "good"
        if loss <= 50
        else "inaccuracy"
        if loss <= 100
        else "mistake"
        if loss <= 200
        else "blunder"
    )


def aggregate(rows, policies):
    scores = []
    for side, name in enumerate(policies):
        moves = [r for r in rows if r["side"] == side]
        n = len(moves)
        scores.append(
            {
                "model": name,
                "color": "white" if side == 0 else "black",
                "moves": n,
                "average_cp_loss": round(sum(r["loss_cp"] for r in moves) / n, 1) if n else None,
                "best_move_matches": sum(r["played"] == r["best"] for r in moves),
                "counts": {
                    label: sum(r["classification"] == label for r in moves)
                    for label in ["excellent", "good", "inaccuracy", "mistake", "blunder"]
                },
                "missed_forced_mates": sum(r["missed_mate"] for r in moves),
                "allowed_forced_mates": sum(r["allowed_mate"] for r in moves),
                "elo": None,
            }
        )
    return scores


def review_game(board, policies, stop, progress=lambda done, total: None):
    replay = board.root()
    rows = []
    moves = board.move_stack
    with chess.engine.SimpleEngine.popen_uci(
        engine_path(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ) as engine:
        engine.configure({"Threads": 1, "Hash": 64})
        name = engine.id.get("name", "Stockfish")
        for i, move in enumerate(moves):
            if stop.is_set():
                raise CancelledError()
            color = replay.turn
            engine.configure({"Clear Hash": None})
            best = engine.analyse(replay, chess.engine.Limit(depth=16, nodes=60000))
            engine.configure({"Clear Hash": None})
            played = (
                best
                if best["pv"][0] == move
                else engine.analyse(
                    replay, chess.engine.Limit(depth=16, nodes=60000), root_moves=[move]
                )
            )
            bs = best["score"].pov(color)
            ps = played["score"].pov(color)

            # Preserve numerical evaluations so errors in winning positions stay visible.
            # Mate scores are mapped far outside normal centipawns; cap LOSS, not positions.
            def cp(score):
                return score.score(mate_score=100000)

            loss = min(2000, max(0, cp(bs) - cp(ps)))
            bm = bs.mate()
            pm = ps.mate()
            rows.append(
                {
                    "ply": i + 1,
                    "side": 0 if color else 1,
                    "san": replay.san(move),
                    "played": move.uci(),
                    "best": best["pv"][0].uci(),
                    "best_san": replay.san(best["pv"][0]),
                    "best_cp": cp(bs),
                    "played_cp": cp(ps),
                    "best_mate": bm,
                    "played_mate": pm,
                    "loss_cp": loss,
                    "classification": classify(loss),
                    "missed_mate": bm is not None and bm > 0 and not (pm is not None and pm > 0),
                    "allowed_mate": pm is not None and pm < 0 and not (bm is not None and bm < 0),
                    "best_depth": best.get("depth"),
                    "played_depth": played.get("depth"),
                    "legal_choices": replay.legal_moves.count(),
                }
            )
            replay.push(move)
            progress(i + 1, len(moves))
    return {
        "engine": name,
        "status": "complete",
        "players": aggregate(rows, policies),
        "moves": rows,
        "method": "Centipawn loss compares the engine best move with the played move. Loss capped at 2000cp per move; mate mapped to +/-100000cp. Inaccuracy >50cp, mistake >100cp, blunder >200cp.",
        "search": "Per move: depth 16 or 60000 nodes, one thread, fresh hash. Best and played move searched separately unless identical; engine first-choice matches have zero loss.",
        "limitations": "Bounded engine search is approximate. Mate transitions and already-decided positions affect centipawn loss. These findings are not a player rating.",
    }

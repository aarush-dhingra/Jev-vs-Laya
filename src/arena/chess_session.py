"""Standard chess, model-selected legal moves, live snapshots and PGN recording."""

import copy
import json
import threading
import time
import uuid
from concurrent.futures import CancelledError

import chess
import chess.pgn

from .providers import ROOT, Budget, ProviderError, jev_config, post_json, settings, validate_answer


def providers_ready():
    import urllib.request

    cfg = jev_config(settings())
    local = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=1) as r:
            local = json.load(r)
    except Exception:
        pass
    return {
        "jev": bool(cfg["key"]),
        "jev_model": cfg["model"],
        "jev_provider": cfg["provider"],
        "laya": local,
    }


class ChessPolicy:
    def __init__(self, name, budget, stop, mode="assisted"):
        if name not in ("jev", "laya"):
            raise ValueError("Select Jev or Laya")
        self.name = name
        self.budget = budget
        self.stop = stop
        self.mode = mode

    def ask(self, state, criteria, instruction):
        if self.stop.is_set():
            raise CancelledError()
        payload = {
            "state": state,
            "questions": {
                "move": {"type": "choice", "instructions": instruction, "criteria": criteria}
            },
        }
        self.budget.take()
        route = None
        if self.name == "jev":
            route = jev_config(settings())
            if not route["key"]:
                raise ProviderError("OpenRouter/Jev key is missing.")
            payload["model"] = route["model"]
            data = post_json(route["url"], payload, route["key"])
        else:
            data = post_json("http://127.0.0.1:8766/predict", payload, timeout=45)
        self.budget.record_usage(data.get("usage"))
        answer = dict(
            validate_answer(
                data, criteria, rounded=bool(route and route["provider"] == "openrouter")
            )
        )
        answer.update(labels=criteria, usage=data.get("usage", {}))
        return answer, data.get("model", self.name)

    def decide(self, board):
        start = time.perf_counter()
        legal = list(board.legal_moves)
        if not legal:
            raise ValueError("No legal moves in a terminal position")
        if self.mode == "assisted":
            from .chess_analysis import prepare

            assistance = prepare(board, self.budget, self.stop)
            state = {
                "fen": board.fen(),
                "turn": "white" if board.turn else "black",
                "recent_moves": assistance["recent_moves"],
                "repeated_position": board.is_repetition(2),
                "material_balance_pawns": assistance.get("material_balance", 0) / 100,
            }
            criteria = {
                r["uci"]: f"{r['san']}: {r['note']}. Opponent could reply {r['reply'] or 'none'}."
                for r in assistance["candidates"]
            }
            answer, model = self.ask(
                state,
                criteria,
                "Play chess to win. Choose between these unranked legal candidates. Consider threats, development and king safety. Avoid repeating when materially ahead. Facts cover only immediate replies; there is no deep engine analysis. Your choice determines the move.",
            )
            move = chess.Move.from_uci(answer["choice"])
            if move not in board.legal_moves:
                raise ProviderError("Illegal model move rejected.")
            return move, {
                "source": self.name,
                "model": model,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "stages": [dict(stage="assisted move", **answer)],
                "assistance": assistance,
            }
        # Identical input and question protocol for both models. Hierarchical
        # choices bound the local checkpoint's 1024-token context without pruning moves.
        state = {
            "fen": board.fen(),
            "board": str(board),
            "turn": "white" if board.turn else "black",
            "check": board.is_check(),
        }
        instruction = "Play standard chess to win. Uppercase pieces are white, lowercase black. Board rows are ranks 8 to 1, columns a to h. Protect your king, avoid losing material, develop pieces and seek checkmate. "
        origins = {
            chess.square_name(m.from_square): chess.piece_name(board.piece_type_at(m.from_square))
            + " on "
            + chess.square_name(m.from_square)
            for m in legal
        }
        first, model = self.ask(
            state,
            origins,
            instruction + "Choose which piece to move; only listed pieces have legal moves.",
        )
        moves = [m for m in legal if chess.square_name(m.from_square) == first["choice"]]
        criteria = {m.uci(): board.san(m) + " (" + m.uci() + ")" for m in moves}
        second, model = self.ask(
            state,
            criteria,
            instruction
            + "Choose the best legal move for the selected piece. SAN + means check; # means mate.",
        )
        move = chess.Move.from_uci(second["choice"])
        if move not in board.legal_moves:
            raise ProviderError("Illegal model move rejected.")
        return move, {
            "source": self.name,
            "model": model,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "stages": [dict(stage="piece", **first), dict(stage="move", **second)],
        }


class ChessSession:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.board = chess.Board()
        self.budget = Budget(1000)
        self.run_dir = None
        self.data = self.initial()

    def restore_latest(self):
        """Restore a completed match for viewing after a server restart; never resume play."""
        paths = sorted((ROOT / "var" / "runs").glob("chess-*/summary.json"), reverse=True)
        if not paths:
            return
        try:
            saved = json.loads(paths[0].read_text(encoding="utf-8"))
            if saved.get("status") != "finished":
                return
            board = chess.Board()
            for row in saved["history"]:
                move = chess.Move.from_uci(row["uci"])
                if move not in board.legal_moves:
                    return
                board.push(move)
                if board.fen() != row["fen"]:
                    return
            if sorted(saved["policies"]) != ["jev", "laya"]:
                return
            with self.lock:
                self.board = board
                self.data.update({k: saved[k] for k in self.data if k in saved})
                self.data.update(thinking=None, thinking_since=None, paused=False)
                self.budget = Budget(saved["budget"])
                self.budget.calls = saved["calls"]
                self.budget.cost_usd = saved["cost_usd"]
                self.run_dir = paths[0].parent
        except (KeyError, ValueError, TypeError, OSError):
            return

    def initial(self):
        return dict(
            review=None,
            review_progress=None,
            mode="assisted",
            status="idle",
            phase="Ready for the first move",
            policies=["jev", "laya"],
            history=[],
            results=[],
            game=1,
            games=1,
            run_id=None,
            error=None,
            result="*",
            termination=None,
            thinking=None,
            thinking_since=None,
            delay=1.0,
            max_plies=400,
            paused=False,
            stats=[{"moves": 0, "total_ms": 0, "last_ms": None} for _ in range(2)],
        )

    def snapshot(self):
        with self.lock:
            data = copy.deepcopy(self.data)
            data.update(
                fen=self.board.fen(),
                turn="white" if self.board.turn else "black",
                check=self.board.is_check(),
                check_square=chess.square_name(self.board.king(self.board.turn))
                if self.board.is_check()
                else None,
                pieces={
                    chess.square_name(s): p.symbol() for s, p in self.board.piece_map().items()
                },
                legal_moves=[m.uci() for m in self.board.legal_moves],
                calls=self.budget.calls,
                budget=self.budget.limit,
                cost_usd=round(self.budget.cost_usd, 9),
                pgn=self.pgn(),
            )
            return data

    def pgn(self):
        game = chess.pgn.Game.from_board(self.board)
        game.headers.update(
            Event="Jev vs Laya · Decision Chess",
            Site="Local",
            Date=time.strftime("%Y.%m.%d"),
            White=self.data["policies"][0].capitalize(),
            Black=self.data["policies"][1].capitalize(),
            Round=str(self.data["game"]),
            Result=self.data["result"],
            Mode=self.data["mode"],
        )
        if self.data.get("termination"):
            game.headers["Termination"] = self.data["termination"]
        return str(game)

    def start(self, options):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("Stop the current match before starting another.")
            names = options.get("policies", ["jev", "laya"])
            if not isinstance(names, list) or len(names) != 2 or sorted(names) != ["jev", "laya"]:
                raise ValueError("Choose Jev versus Laya, one model per color.")
            mode = options.get("mode", "assisted")
            if mode not in ("assisted", "unassisted"):
                raise ValueError("Unknown play mode")
            if mode == "assisted":
                from .chess_review import engine_path

                engine_path()
            delay = float(options.get("delay", 1))
            games = int(options.get("games", 1))
            limit = int(options.get("budget", 1000))
            plies = int(options.get("max_plies", 400))
            if (
                not 0.25 <= delay <= 5
                or games not in (1, 2)
                or not 4 <= limit <= 2000
                or not 2 <= plies <= 600
            ):
                raise ValueError("Match settings out of range.")
            ready = providers_ready()
            if not ready["jev"]:
                raise ProviderError("Add your OpenRouter key to .env.")
            if not ready["laya"]:
                raise ProviderError("Start the local Laya worker with Start-Local.ps1.")
            self.stop_event = threading.Event()
            self.wake = threading.Event()
            self.budget = Budget(limit)
            self.board = chess.Board()
            self.data = self.initial()
            self.data.update(
                mode=mode,
                status="running",
                phase="Match starting",
                policies=names.copy(),
                games=games,
                delay=delay,
                max_plies=plies,
                run_id="chess-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
            )
            self.run_dir = ROOT / "var" / "runs" / self.data["run_id"]
            self.run_dir.mkdir(parents=True)
            (self.run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "game": "standard chess",
                        "rules_version": chess.__version__,
                        "policies": names,
                        "games": games,
                        "delay": delay,
                        "budget": limit,
                        "max_plies": plies,
                        "claim_draws": True,
                        "mode": mode,
                        "decision_protocol": "shared-lightweight-v1, two plies + board facts + model choice; Stockfish post-game only"
                        if mode == "assisted"
                        else "choose legal origin, then legal move",
                    },
                    indent=2,
                )
            )
            self.thread = threading.Thread(target=self.run, args=(names.copy(),), daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            self.wake.set()
            if self.data["status"] in ("running", "paused", "reviewing"):
                self.data.update(
                    status="stopping", phase="Stopping; pending responses will be discarded"
                )

    def pause(self):
        with self.lock:
            if self.data["status"] not in ("running", "paused"):
                raise ValueError("No active game to pause.")
            self.data["paused"] = not self.data["paused"]
            self.data["status"] = "paused" if self.data["paused"] else "running"
            self.data["phase"] = "Paused" if self.data["paused"] else "Resuming"
            self.wake.set()

    def wait_if_paused(self):
        while not self.stop_event.is_set():
            with self.lock:
                if not self.data["paused"]:
                    return
            self.wake.wait(0.1)
            self.wake.clear()
        raise CancelledError()

    def apply(self, move, decision):
        # Called under lock; validation happens again on the current position.
        if move not in self.board.legal_moves:
            raise ProviderError("Illegal or stale move rejected.")
        before = self.board.fen()
        san = self.board.san(move)
        side = 0 if self.board.turn else 1
        captured = self.board.piece_at(move.to_square)
        if self.board.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not self.board.turn)
        self.board.push(move)
        row = {
            "ply": len(self.board.move_stack),
            "uci": move.uci(),
            "san": san,
            "side": side,
            "before": before,
            "fen": self.board.fen(),
            "captured": captured.symbol() if captured else None,
            **decision,
        }
        self.data["history"].append(row)
        stat = self.data["stats"][side]
        stat["moves"] += 1
        stat["total_ms"] += decision["latency_ms"]
        stat["last_ms"] = decision["latency_ms"]
        if self.run_dir:
            with (self.run_dir / "moves.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"game": self.data["game"], **row}) + "\n")

    def finish_board(self):
        outcome = self.board.outcome(claim_draw=True)
        if not outcome:
            return False
        self.data.update(
            result=outcome.result(), termination=outcome.termination.name.lower().replace("_", " ")
        )
        return True

    def save(self):
        if self.run_dir:
            (self.run_dir / "summary.json").write_text(
                json.dumps(self.snapshot(), indent=2), encoding="utf-8"
            )
            (self.run_dir / f"game-{self.data['game']}.pgn").write_text(
                self.pgn(), encoding="utf-8"
            )

    def run(self, original):
        try:
            for game_index in range(self.data["games"]):
                self.wait_if_paused()
                with self.lock:
                    self.board = chess.Board()
                    self.data.update(
                        review=None,
                        review_progress=None,
                        game=game_index + 1,
                        policies=original if game_index % 2 == 0 else original[::-1],
                        history=[],
                        result="*",
                        termination=None,
                        stats=[{"moves": 0, "total_ms": 0, "last_ms": None} for _ in range(2)],
                    )
                while not self.stop_event.is_set():
                    self.wait_if_paused()
                    with self.lock:
                        if self.finish_board():
                            break
                        if len(self.board.move_stack) >= self.data["max_plies"]:
                            self.data.update(
                                termination="Move limit reached · unfinished",
                                phase="Move limit reached",
                            )
                            self.stop_event.set()
                            break
                        board = self.board.copy()
                        side = 0 if board.turn else 1
                        name = self.data["policies"][side]
                        self.data.update(
                            thinking=name,
                            thinking_since=time.time(),
                            phase=name.capitalize() + " is thinking",
                        )
                    move, decision = ChessPolicy(
                        name, self.budget, self.stop_event, self.data["mode"]
                    ).decide(board)
                    self.wait_if_paused()
                    with self.lock:
                        if self.stop_event.is_set():
                            break
                        self.apply(move, decision)
                        self.finish_board()
                        self.data.update(
                            thinking=None,
                            thinking_since=None,
                            phase=f"{name.capitalize()} played {self.data['history'][-1]['san']}",
                        )
                        self.save()
                    if self.stop_event.wait(self.data["delay"]):
                        break
                with self.lock:
                    if self.stop_event.is_set():
                        break
                    self.data["results"].append(
                        {
                            "game": game_index + 1,
                            "policies": self.data["policies"].copy(),
                            "result": self.data["result"],
                            "termination": self.data["termination"],
                            "plies": len(self.board.move_stack),
                            "pgn": self.pgn(),
                        }
                    )
                    self.save()
                # No review output can reach a live decision: this runs only after the game ends.
                with self.lock:
                    completed_board = self.board.copy()
                    policies = self.data["policies"].copy()
                    self.data.update(
                        status="reviewing",
                        phase="Stockfish reviewing the finished game",
                        review_progress={"done": 0, "total": len(completed_board.move_stack)},
                    )

                def progress(done, total):
                    with self.lock:
                        self.data.update(
                            review_progress={"done": done, "total": total},
                            phase=f"Stockfish review {done}/{total} half-moves",
                        )

                try:
                    from .chess_review import review_game

                    report = review_game(completed_board, policies, self.stop_event, progress)
                    with self.lock:
                        self.data["review"] = report
                        self.data["results"][-1]["review"] = report
                        (self.run_dir / f"review-{game_index + 1}.json").write_text(
                            json.dumps(report, indent=2), encoding="utf-8"
                        )
                except CancelledError:
                    raise
                except Exception as exc:
                    with self.lock:
                        self.data["review"] = {
                            "status": "error",
                            "error": str(exc)
                            if isinstance(exc, ProviderError)
                            else type(exc).__name__,
                        }
                with self.lock:
                    self.save()
                if game_index + 1 < self.data["games"]:
                    if self.stop_event.wait(3):
                        break
                    with self.lock:
                        self.data.update(status="running")
            with self.lock:
                stopped = self.stop_event.is_set()
                self.data.update(
                    status="stopped" if stopped else "finished",
                    phase="Match stopped" if stopped else self.data["termination"].capitalize(),
                )
        except CancelledError:
            with self.lock:
                self.data.update(status="stopped", phase="Match stopped")
        except Exception as exc:
            with self.lock:
                self.data.update(
                    status="error",
                    phase="Match stopped",
                    error=str(exc)
                    if isinstance(exc, (ProviderError, ValueError))
                    else type(exc).__name__,
                )
        finally:
            with self.lock:
                self.data.update(thinking=None, thinking_since=None, paused=False)
                if self.data["result"] == "*" and not self.data["termination"]:
                    self.data["termination"] = "Unfinished"
                self.save()

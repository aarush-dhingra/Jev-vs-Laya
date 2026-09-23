"""Identical two-ply, handcrafted assistance for both players. No Stockfish/API."""

from concurrent.futures import CancelledError

import chess

VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def history(board):
    replay = board.root()
    moves = []
    for move in board.move_stack:
        moves.append(replay.san(move))
        replay.push(move)
    return moves[-12:]


def material(board, color):
    return sum(
        v * (len(board.pieces(p, color)) - len(board.pieces(p, not color)))
        for p, v in VALUES.items()
    )


def evaluate(board, color):
    if board.is_checkmate():
        return -100000 if board.turn == color else 100000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    score = material(board, color)
    non_pawn = sum(
        VALUES[p.piece_type] for p in board.piece_map().values() if p.piece_type != chess.PAWN
    )
    for sq, piece in board.piece_map().items():
        f = chess.square_file(sq)
        r = chess.square_rank(sq)
        advance = r if piece.color else 7 - r
        center = 3.5 - abs(f - 3.5) + 3.5 - abs(r - 3.5)
        value = 0
        if piece.piece_type == chess.PAWN:
            value = advance * 8 + center * 4 + (40 if advance == 6 else 0)
        elif piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            value = center * 9 + (15 if advance > 0 else 0)
        elif piece.piece_type == chess.ROOK:
            value = advance * 2
        elif piece.piece_type == chess.KING:
            value = (
                center * 8
                if non_pawn < 2200
                else (35 if advance == 0 and f in (2, 6) else -advance * 12)
            )
        score += value if piece.color == color else -value
    return score


def facts(board, move):
    color = board.turn
    piece = board.piece_at(move.from_square)
    after = board.copy()
    after.push(move)
    replies = list(after.legal_moves)
    worst = evaluate(after, color)
    reply_san = None
    mate_threat = False
    if replies:
        worst = 1000000
        for reply in replies:
            san = after.san(reply)
            after.push(reply)
            value = evaluate(after, color)
            if after.is_checkmate():
                mate_threat = True
            after.pop()
            if value < worst:
                worst = value
                reply_san = san
    capture = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        capture = chess.Piece(chess.PAWN, not color)
    threatened = bool(after.is_attacked_by(not color, move.to_square))
    defended = bool(after.is_attacked_by(color, move.to_square))
    development = piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(
        move.from_square
    ) == (0 if color else 7)
    category = (
        "attack"
        if capture or after.is_check()
        else "develop"
        if development or board.is_castling(move)
        else "improve"
    )
    if board.is_check() or (board.is_attacked_by(not color, move.from_square) and not threatened):
        category = "defend"
    repeat = after.is_repetition(2)
    draw = (
        after.can_claim_threefold_repetition()
        or after.can_claim_fifty_moves()
        or after.is_stalemate()
    )
    parts = [category]
    if capture:
        parts.append("captures " + chess.piece_name(capture.piece_type))
    if after.is_checkmate():
        parts.append("checkmate now")
    elif after.is_check():
        parts.append("check")
    if board.is_castling(move):
        parts.append("castles")
    if move.promotion:
        parts.append("promotes to " + chess.piece_name(move.promotion))
    if threatened:
        parts.append("destination attacked" + (" and defended" if defended else ", undefended"))
    if mate_threat:
        parts.append("allows mate next reply")
    if repeat:
        parts.append("repeats position")
    if draw:
        parts.append("allows draw claim")
    return {
        "uci": move.uci(),
        "san": board.san(move),
        "category": category,
        "note": "; ".join(parts),
        "reply": reply_san,
        "repeat": repeat,
        "draw": draw,
        "mate_now": after.is_checkmate(),
        "allows_mate": mate_threat,
        "material_balance": material(after, color),
        "heuristic": round(worst, 1),
    }


def candidates(board, stop=None):
    rows = []
    for move in board.legal_moves:
        if stop and stop.is_set():
            raise CancelledError()
        rows.append(facts(board, move))
    if not rows:
        raise ValueError("Terminal position has no candidates")
    mates = [r for r in rows if r["mate_now"]]
    safe = mates or [r for r in rows if not r["allows_mate"]] or rows
    # A shared safety rule; no deep evaluation, opening book, or engine ranking.
    if material(board, board.turn) > 100:
        progress = [r for r in safe if not r["repeat"] and not r["draw"]]
        if progress:
            safe = progress
    ranked = sorted(safe, key=lambda r: (-r["heuristic"], r["uci"]))
    chosen = []
    for category in ("attack", "defend", "develop", "improve"):
        choice = next((r for r in ranked if r["category"] == category), None)
        if choice:
            chosen.append(choice)
    for row in ranked:
        if len(chosen) >= 4:
            break
        if row not in chosen:
            chosen.append(row)
    chosen = sorted(chosen[:4], key=lambda r: r["uci"])
    return chosen, "Lightweight v1 · two plies"


def prepare(board, budget, stop):
    rows, engine = candidates(board, stop)
    return {
        "engine": engine,
        "analyst": "Deterministic board facts (no hosted analyst)",
        "warning": None,
        "candidates": rows,
        "recent_moves": history(board),
        "material_balance": material(board, board.turn),
        "protocol": "shared-lightweight-v1: all legal moves + immediate replies; diverse categories; unranked model options; no Stockfish",
        "search_plies": 2,
        "stockfish_used": False,
    }

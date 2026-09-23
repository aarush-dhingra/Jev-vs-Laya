"""Read-only chess diagnostics; never prints credential values."""

import json
import platform

import chess

from arena.chess_session import providers_ready


def diagnose():
    return {
        "game": "standard chess",
        "python": platform.python_version(),
        "chess": chess.__version__,
        "providers": providers_ready(),
    }


if __name__ == "__main__":
    print(json.dumps(diagnose(), indent=2))

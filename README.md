# Jev vs Laya

A local arena for comparing Jev and Laya through games. Chess is the first implemented game.

Watch two decision models play standard chess on a live board, inspect their choices, replay moves, and download PGNs. Both use identical lightweight candidate generation. Stockfish reviews finished games only.

## Quick start (Windows, Python 3.12)

```powershell
git clone https://github.com/aarush-dhingra/Jev-vs-Laya.git
cd Jev-vs-Laya
.\scripts\Install.ps1 -Models
.\scripts\Install-ChessEngine.ps1
# Set your OPENROUTER_API_KEY in .env
.\scripts\Start-Local.ps1
```

Open http://127.0.0.1:8765. Laya downloads its weights on first launch and uses CUDA when available, otherwise CPU. Jev calls require your own OpenRouter access. See [setup](docs/setup.md) for device configuration and troubleshooting.

Stop services with `.\scripts\Stop-Local.ps1`. Closing the browser does not stop play.

## How it works

1. Generate legal moves and examine each immediate opponent reply.
2. Evaluate material, piece placement, pawn progress, and basic king placement.
3. Offer up to four diverse candidates using the same method for both players.
4. Let Jev or Laya select the move, validate it, and animate it.
5. After the game, run Stockfish to measure centipawn loss, mistakes, blunders, and missed/allowed mates.

Models receive position facts and recent history; numeric candidate rankings are not sent to them. Invalid model responses stop play. The unassisted piece-then-move mode remains available. Claimable repetition and fifty-move draws are claimed automatically. Games are untimed; decision timers measure latency.

Stockfish review uses depth 16 or 60,000 nodes per search. Loss is capped at 2,000cp; mate scores map to +/-100,000cp. Thresholds are excellent <=20cp, good <=50cp, inaccuracy <=100cp, mistake <=200cp, and blunder >200cp. These bounded-search findings are estimates, not player ratings. Shared shallow assistance affects results, and a single game does not establish general model strength.

## Project layout

```text
src/arena/       Chess logic, provider adapters, local services
  web/          Dashboard HTML, CSS, and JavaScript
scripts/        Windows installation and service commands
tests/          Offline unit and HTTP integration tests
docs/           Setup and third-party notices
.github/        CI, contribution and security guidance
var/            Ignored local models, engines, logs, and match data
pyproject.toml  Package metadata, dependencies, and lint settings
```

## Development

```powershell
.\scripts\Install.ps1
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
node --check src/arena/web/app.js
```

Tests do not require credentials, model downloads, or paid calls. See [contributing](.github/CONTRIBUTING.md).

## Models and license

Jev uses TypeSafe's decision API through OpenRouter. Laya uses the `laya` Python package and Convai Innovations' `convaiinnovations/laya` typed-decisions checkpoint, not `mizorewww/laya-mlx`.

Project code is [GPL-3.0-or-later](LICENSE). Chess rules and SVG pieces come from python-chess. Stockfish, model weights, and other dependencies retain their own licenses and terms; see [third-party notices](docs/third-party-notices.md). Credentials and runtime data are excluded from Git.

## Roadmap

Future work will extend the arena to more games while preserving a fair comparison between Jev and Laya. These items are planned, not implemented:

- Extract a shared game interface for observations, legal actions, applying moves, and terminal results.
- Add small deterministic games such as Connect Four and Reversi before more complex environments.
- Give both players identical visible information, action choices, and assistance settings within each game.
- Run repeatable series with swapped sides, recorded model versions, and per-game metrics.
- Reuse live spectating, replay, decision inspection, and exports across games.

Chess-specific evaluation and Stockfish review will remain separate from the shared game interface. New games should include rule tests and an offline deterministic baseline before model integration.

Suggestions and contributions are welcome through [issues](https://github.com/aarush-dhingra/Jev-vs-Laya/issues) and pull requests. Maintained by [aarush-dhingra](https://github.com/aarush-dhingra).

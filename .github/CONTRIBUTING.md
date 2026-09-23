# Contributing

Use Python 3.12. For code changes without running models:

```powershell
.\scripts\Install.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --check src/arena/web/app.js
```

Node.js is needed only for the optional JavaScript syntax check. Unit tests use mocks and do not make paid model calls.

Keep both players on the same candidate-generation protocol. Never substitute a heuristic move for an invalid model response. Stockfish must remain outside the live decision path. Add focused regression tests when changing chess rules, provider validation, or session behavior.

Do not submit credentials, local configurations, logs, match records, downloaded engines, model weights, or recordings. Review `git diff --cached` before committing. Contributions are provided under GPL-3.0-or-later.

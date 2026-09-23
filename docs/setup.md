# Setup guide

The supported launcher workflow is Windows PowerShell with Python 3.12. The dashboard runs locally at http://127.0.0.1:8765 and the Laya worker at http://127.0.0.1:8766.

## 1. Prerequisites

- Install Python 3.12 and make `python` available in PowerShell.
- Install Git.
- Have an OpenRouter API key with access to the configured Jev decision model.
- Allow internet access for package installation, the initial Laya checkpoint download, Stockfish installation, and hosted Jev requests.
- An NVIDIA GPU with compatible drivers is optional. CPU mode is supported but slower. Model memory requirements depend on the checkpoint and PyTorch device configuration.

Check your tools:

```powershell
python --version
git --version
```

Node.js is needed only for the JavaScript development check, not to run the dashboard.

## 2. Clone and install

```powershell
git clone https://github.com/aarush-dhingra/Jev-vs-Laya.git
cd Jev-vs-Laya
.\scripts\Install.ps1 -Models
.\scripts\Install-ChessEngine.ps1
```

`Install.ps1` creates `.venv`, installs the project in editable mode, and installs local model dependencies with `-Models`. It creates `.env` from `.env.example` only if that file does not already exist. The engine installer downloads Stockfish for Windows into `var/tools/` with its source and license.

If your PowerShell policy blocks scripts, follow your device's execution-policy rules. On a personal machine, you can invoke a reviewed script for this process only with `powershell -ExecutionPolicy Bypass -File .\scripts\Install.ps1 -Models`.

## 3. Configure Jev

Open `.env` in your editor:

```powershell
notepad .env
```

Set these values, replacing the placeholder with your own key:

```dotenv
OPENROUTER_API_KEY=your-key-here
JEV_PROVIDER=openrouter
JEV_MODEL=typesafe/jev-1.13
```

The model identifier and account access must be supported by your provider. Requests may incur charges. `OPEN_ROUTER_API_KEY` is also accepted as an alias. Never commit `.env`; `.gitignore` excludes it. Environment variables override values from `.env`.

For the optional direct TypeSafe route, set `JEV_PROVIDER=typesafe`, `JEV_MODEL=jev-latest`, and `JEV_API_KEY` to the corresponding direct-provider key.

## 4. Choose the local Laya device

The worker uses CUDA when available and otherwise falls back to CPU. It loads the `convaiinnovations/laya` typed-decisions checkpoint through the `laya` Python package. This is not the `laya-mlx` implementation.

Check your installed PyTorch build:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print('CUDA available:', torch.cuda.is_available())"
```

For GPU use, choose a compatible CUDA build using the [official PyTorch installer](https://pytorch.org/get-started/locally/), running its installation command with `.\.venv\Scripts\python.exe -m pip` so it targets this environment. The project pins its tested PyTorch version in `pyproject.toml`; check compatibility before changing it.

## 5. Start and check readiness

```powershell
.\scripts\Start-Local.ps1
.\scripts\Doctor.ps1
```

Open http://127.0.0.1:8765. On the first launch, allow time for the Laya checkpoint to download and load. Refresh provider readiness after it finishes. The doctor reports configured credentials and worker readiness without printing key values; actual Jev account access is checked when a request is made.

To force CPU mode, stop an existing worker first:

```powershell
.\scripts\Stop-Local.ps1
.\scripts\Start-Local.ps1 -Device cpu
```

## 6. Play and inspect a match

Select **Lightweight / shared analysis** and start a match. Both players receive the same candidate-generation method. Stockfish reviews the game only after it ends. Its findings are bounded-search estimates, not player ratings.

Click a move to replay it, or Live to follow the current position. Pause/Resume controls play; Stop cancels. Download the PGN to save the game. Select two games to swap colors. A fresh clone starts without saved games; later launches restore the latest completed local game.

Closing the browser does not stop a match. Shut down both services with:

```powershell
.\scripts\Stop-Local.ps1
```

To stop only the dashboard, use `-Service server`; to stop only the model worker, use `-Service laya`.

## Local files

| Location | Contents |
| --- | --- |
| `.env` | Private provider configuration |
| `.venv/` | Python environment |
| `var/cache/` | Downloaded model files |
| `var/tools/` | Stockfish distribution |
| `var/logs/` | Service output and errors |
| `var/runs/` | Match records, PGNs, and reviews |

These paths are excluded from Git. For an installed wheel, set `DECISION_CHESS_HOME` to a writable directory containing `.env` and `var/`; outside an editable checkout the default is the current directory. Windows launcher scripts assume an editable checkout. Dashboard assets are included in the package.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Missing Jev credentials or HTTP error | `.env`, model access, provider balance, and network connection |
| Laya not ready | `var/logs/laya-worker-error.log`; wait for the initial download |
| CUDA unavailable | Compatible drivers and PyTorch build, or use CPU mode |
| Missing reviewer | Rerun `.\scripts\Install-ChessEngine.ps1` |
| Dashboard unavailable | `var/logs/server-error.log` and whether port 8765 is occupied |
| Dependency conflicts after updating | Reinstall the project extras in the intended `.venv` and run the checks below |

Services bind to localhost. Public hosting requires additional authentication and deployment work.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
node --check src/arena/web/app.js
.\.venv\Scripts\python.exe -m build
```

Automated tests do not require credentials, model downloads, or paid model requests. Live model integration needs the setup above. See [contributing](../.github/CONTRIBUTING.md) for code and fairness requirements.

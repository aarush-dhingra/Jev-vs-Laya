# Third-party components

- **python-chess / chess 1.11.2** provides chess rules and SVG piece artwork. Copyright Niklas Fiekas and contributors. GPL-3.0-or-later. Source: https://github.com/niklasf/python-chess
- **Stockfish** provides optional post-game analysis. GPL-3.0. Downloaded separately by `Install-ChessEngine.ps1`; not vendored in this repository. Source: https://github.com/official-stockfish/Stockfish
- **Laya** uses the separately installed `laya` package and `convaiinnovations/laya` checkpoint, downloaded by the local worker. Package: https://pypi.org/project/laya/ ; model: https://huggingface.co/convaiinnovations/laya . Consult those distributions for their licenses and model terms. The project's GPL license does not relicense model weights.
- **Jev** is accessed through OpenRouter's hosted decision API. No Jev weights are distributed here. Hosted-service access is subject to the provider's terms.

Other dependencies retain their own licenses. This project is not affiliated with Chess.com, TypeSafe, Convai Innovations, OpenRouter, or the Stockfish team.

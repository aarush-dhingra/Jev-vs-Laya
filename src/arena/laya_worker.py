"""Separate resident model process: python laya_worker.py [--device cpu|cuda]."""

import argparse
import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .providers import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--checkpoint", default="convaiinnovations/laya")
    parser.add_argument("--subfolder", default="typed-decisions")
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(ROOT / "var" / "cache" / "huggingface"))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import laya
    import torch

    if args.device == "auto":
        args.device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit(
            "CUDA unavailable in this Python environment. Install CUDA PyTorch or use --device cpu."
        )
    print("Loading Laya. First launch downloads its open weights.", flush=True)
    model_path = Path(args.checkpoint)
    if not model_path.exists():
        from huggingface_hub import snapshot_download

        prefix = (args.subfolder + "/") if args.subfolder else ""
        # local_dir avoids Windows symlink privileges and keeps all downloaded files in this project.
        model_path = ROOT / "var" / "cache" / "models" / args.checkpoint.replace("/", "--")
        snapshot_download(
            args.checkpoint,
            local_dir=str(model_path),
            allow_patterns=[
                prefix + n
                for n in ("rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*")
            ],
        )
    agent = laya.load(
        str(model_path.resolve()), device=args.device, subfolder=args.subfolder or None
    )
    # Preserve the checkpoint context budget; reject oversized observations instead of silently truncating.
    from laya.common import build_sequence

    lock = threading.Lock()
    metadata = (
        model_path
        / ".cache"
        / "huggingface"
        / "download"
        / args.subfolder
        / "rl_agent_config.json.metadata"
    )
    revision = metadata.read_text().splitlines()[0] if metadata.exists() else "local"
    cfg_path = model_path / args.subfolder / "rl_agent_config.json"
    info = dict(
        ready=True,
        checkpoint=args.checkpoint,
        subfolder=args.subfolder,
        revision=revision,
        config_sha256=hashlib.sha256(cfg_path.read_bytes()).hexdigest(),
        device=str(agent.device),
        version=getattr(laya, "__version__", "unknown"),
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, data):
            content = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            self.send(200, info) if self.path == "/health" else self.send(
                404, {"error": "Not found"}
            )

        def do_POST(self):
            if self.path != "/predict":
                return self.send(404, {"error": "Not found"})
            if self.headers.get("Origin"):
                return self.send(403, {"error": "Browser calls disabled"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100_000:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(length))
                with lock:
                    q = data["questions"]["move"]
                    internal = agent._to_internal(q)
                    # Check token count with a generous virtual sequence before model truncation.
                    seq, _ = build_sequence(
                        agent.tok,
                        data["state"],
                        internal,
                        100_000,
                        agent.cfg.get("head_max_len", 256),
                    )
                    if len(seq) > agent.cfg.get("max_len", 1024):
                        return self.send(
                            422,
                            {
                                "error": "Observation exceeds checkpoint context budget. Reduce visible-state size or use a compatible longer-context checkpoint."
                            },
                        )
                    result = agent.predict(data["state"], data["questions"])
                    result["model"] = (
                        f"{args.checkpoint}/{args.subfolder}@{revision[:12]} (laya {info['version']})"
                    )
                self.send(200, result)
            except Exception as e:
                self.send(422, {"error": type(e).__name__})

    print("Laya ready at http://127.0.0.1:8766", info, flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()


if __name__ == "__main__":
    main()

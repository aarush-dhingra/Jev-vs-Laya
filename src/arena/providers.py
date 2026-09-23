"""Provider adapters with one shared question contract and strict result validation."""

from __future__ import annotations

import json
import math
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

_checkout = Path(__file__).resolve().parents[2]
ROOT = Path(
    os.environ.get(
        "DECISION_CHESS_HOME", _checkout if (_checkout / "pyproject.toml").exists() else Path.cwd()
    )
).resolve()


def settings():
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return {**values, **os.environ}


class ProviderError(RuntimeError):
    pass


def openrouter_key(env):
    return env.get("OPENROUTER_API_KEY") or env.get("OPEN_ROUTER_API_KEY")


def jev_config(env):
    provider = env.get("JEV_PROVIDER") or ("openrouter" if openrouter_key(env) else "typesafe")
    if provider not in ("openrouter", "typesafe"):
        raise ProviderError("JEV_PROVIDER must be openrouter or typesafe.")
    if provider == "openrouter":
        model = env.get("JEV_MODEL") or "typesafe/jev-1.13"
        if model == "jev-latest":
            model = "typesafe/jev-1.13"
        return dict(
            provider=provider,
            url="https://openrouter.ai/api/alpha/decisions",
            model=model,
            key=openrouter_key(env),
        )
    return dict(
        provider=provider,
        url="https://api.typesafe.ai/v1/systemone",
        model=env.get("JEV_MODEL") or "jev-latest",
        key=env.get("JEV_API_KEY") or env.get("TYPESAFE_API_KEY"),
    )


class Budget:
    def __init__(self, limit=500):
        self.limit = limit
        self.calls = 0
        self.cost_usd = 0.0
        self.priced_responses = 0
        self.lock = threading.Lock()

    def take(self):
        with self.lock:
            if self.calls >= self.limit:
                raise ProviderError("Request budget reached. Start a new session to continue.")
            self.calls += 1

    def record_usage(self, usage):
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if (
            isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
        ):
            with self.lock:
                self.cost_usd += cost
                self.priced_responses += 1


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def post_json(url, payload, key=None, timeout=20):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(
        url, json.dumps(payload, allow_nan=False).encode(), headers, method="POST"
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            return json.loads(response.read(4_000_000))
    except urllib.error.HTTPError as e:
        if url.startswith("http://127.0.0.1:8766/") and e.code == 422:
            raise ProviderError(
                "Local Laya rejected the observation. Check the worker log and checkpoint context budget; no action was executed."
            ) from None
        raise ProviderError(
            f"Provider HTTP {e.code}. Check access, configured model and account limits."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("Provider connection failed or timed out.") from None
    except (ValueError, TypeError):
        raise ProviderError("Provider returned invalid JSON.") from None


def validate_answer(data, criteria, rounded=False):
    try:
        answer = data["answers"]["move"]
        probs = answer["probabilities"]
        if answer.get("type") != "choice" or answer["choice"] not in criteria:
            raise ValueError()
        if set(probs) != set(criteria):
            raise ValueError()
        if any(
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not math.isfinite(v)
            or v < 0
            or v > 1
            for v in probs.values()
        ):
            raise ValueError()
        tolerance = max(0.025, len(criteria) * 0.005 + 1e-9) if rounded else 0.025
        if abs(sum(probs.values()) - 1) > tolerance:
            raise ValueError()
        return answer
    except (KeyError, TypeError, ValueError):
        raise ProviderError(
            "Invalid model choice or probability distribution; no action executed."
        ) from None

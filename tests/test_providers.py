import math
import unittest

from arena.providers import Budget, ProviderError, jev_config, validate_answer


class ProviderTests(unittest.TestCase):
    def test_openrouter_alias_and_model_route(self):
        config = jev_config({"OPEN_ROUTER_API_KEY": "test-key", "JEV_MODEL": "jev-latest"})
        self.assertEqual(config["url"], "https://openrouter.ai/api/alpha/decisions")
        self.assertEqual(config["model"], "typesafe/jev-1.13")
        self.assertEqual(config["key"], "test-key")

    def test_direct_route_keeps_credentials_separate(self):
        config = jev_config(
            {"JEV_PROVIDER": "typesafe", "JEV_API_KEY": "direct", "OPENROUTER_API_KEY": "router"}
        )
        self.assertEqual(config["key"], "direct")
        self.assertEqual(config["provider"], "typesafe")
        with self.assertRaises(ProviderError):
            jev_config({"JEV_PROVIDER": "unknown"})

    def test_invalid_distributions_are_rejected(self):
        for probabilities in (
            {"a": math.nan, "b": 0},
            {"a": True, "b": 0},
            {"a": 0.1, "b": 0.1},
            {"a": 1},
            {"a": 1.1, "b": -0.1},
        ):
            with self.subTest(probabilities=probabilities), self.assertRaises(ProviderError):
                validate_answer(
                    {
                        "answers": {
                            "move": {
                                "type": "choice",
                                "choice": "a",
                                "probabilities": probabilities,
                            }
                        }
                    },
                    {"a": "A", "b": "B"},
                )

    def test_unknown_move_is_rejected(self):
        with self.assertRaises(ProviderError):
            validate_answer(
                {"answers": {"move": {"type": "choice", "choice": "c", "probabilities": {"a": 1}}}},
                {"a": "A"},
            )

    def test_budget_and_invalid_usage(self):
        budget = Budget(1)
        budget.take()
        with self.assertRaises(ProviderError):
            budget.take()
        for cost in (True, -1, math.inf, math.nan, "1"):
            budget.record_usage({"cost": cost})
        self.assertEqual(budget.cost_usd, 0)
        budget.record_usage({"cost": 0.25})
        self.assertEqual(budget.cost_usd, 0.25)

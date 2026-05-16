import os
import unittest
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.services import paper_exit_config, promotion_readiness  # noqa: E402


class SymbolExitConfigTests(unittest.TestCase):
    def test_symbol_override_merges_with_global_config(self):
        with patch.object(paper_exit_config.settings, "paper_exit_mode", "author_part_book_trail"), \
            patch.object(paper_exit_config.settings, "paper_part_book_r_multiple", 1.0), \
            patch.object(paper_exit_config.settings, "paper_part_book_fraction", 0.5), \
            patch.object(paper_exit_config.settings, "paper_trail_lookback_candles", 3), \
            patch.object(paper_exit_config.settings, "paper_trade_cooldown_candles", 5), \
            patch.object(
                paper_exit_config.settings,
                "paper_symbol_exit_overrides",
                '{"NIFTY":{"part_book_r_multiple":0.75,"trail_lookback_candles":4}}',
            ):
            config = paper_exit_config.paper_exit_config_for_symbol("nifty")

        self.assertEqual(config["source"], "symbol_override")
        self.assertEqual(config["part_book_r_multiple"], 0.75)
        self.assertEqual(config["part_book_fraction"], 0.5)
        self.assertEqual(config["trail_lookback_candles"], 4)


class SymbolPromotionReadinessTests(unittest.TestCase):
    def test_nifty_replay_ready_but_forward_paper_blocked(self):
        tuning_report = {
            "available": True,
            "name": "nifty_sell_tuning.json",
            "report": {
                "generated_at": "2026-05-16T16:10:33",
                "mode": "grid",
                "baseline_sell": {"max_drawdown_points": 500},
                "top_candidates": [
                    {
                        "config": {
                            "part_book_r_multiple": 0.75,
                            "part_book_fraction": 0.6,
                            "trail_lookback_candles": 4,
                            "cooldown_candles": 5,
                        }
                    }
                ],
            },
        }
        replay_report = {
            "available": True,
            "name": "replay_risk_report.json",
            "report": {
                "config": {
                    "exit_mode": "author_part_book_trail",
                    "part_book_r_multiple": 0.75,
                    "part_book_fraction": 0.6,
                    "trail_lookback_candles": 4,
                    "cooldown_candles": 5,
                },
                "symbols": [
                    {
                        "symbol": "NIFTY",
                        "metrics": {
                            "trades": 500,
                            "profit_factor": 3.12,
                            "profit_factor_label": "3.12",
                            "max_drawdown_points": 180,
                        },
                        "by_side": [
                            {
                                "side": "sell",
                                "profit_factor": 3.55,
                                "profit_factor_label": "3.55",
                                "max_drawdown_points": 180,
                            }
                        ],
                    }
                ],
            },
        }
        scheduler = {
            "effective_exit_by_symbol": {
                "NIFTY": {
                    "exit_mode": "author_part_book_trail",
                    "part_book_r_multiple": 0.75,
                    "part_book_fraction": 0.6,
                    "trail_lookback_candles": 4,
                    "cooldown_candles": 5,
                    "source": "symbol_override",
                }
            }
        }
        performance = {
            "items": [
                {
                    "symbol": "NIFTY",
                    "realized_closed_trades": 1,
                    "gross_loss": 0,
                    "net_realized_pnl": 50,
                    "profit_factor": None,
                    "profit_factor_label": "Infinite",
                }
            ]
        }

        with patch.object(promotion_readiness, "sell_tuning_report", return_value=tuning_report), \
            patch.object(promotion_readiness, "latest_replay_risk_report", return_value=replay_report), \
            patch.object(promotion_readiness, "paper_scheduler_config", return_value=scheduler), \
            patch.object(promotion_readiness, "paper_performance_metrics", return_value=performance), \
            patch.object(promotion_readiness, "_author_source_count", return_value=10), \
            patch.object(promotion_readiness.settings, "enable_live_trading", False):
            result = promotion_readiness.build_symbol_promotion_readiness(object(), symbol="NIFTY")

        self.assertEqual(result["symbol"], "NIFTY")
        self.assertTrue(result["ready_for_paper_candidate_review"])
        self.assertFalse(result["ready_for_live_candidate_review"])
        self.assertIn("forward_paper_sample_ready", result["live_candidate_blocking_gates"])
        self.assertEqual(result["effective_paper_scheduler"]["source"], "symbol_override")


if __name__ == "__main__":
    unittest.main()

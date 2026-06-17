"""Config loader helpers."""

from __future__ import annotations

from src.config_loader import load_config, stock_rs_min_daily_dollar_volume


def test_stock_rs_min_daily_dollar_volume_prefers_new_key() -> None:
    rs = {"min_daily_dollar_volume_usd": 50_000_000}
    assert stock_rs_min_daily_dollar_volume(rs) == 50_000_000.0


def test_stock_rs_min_daily_dollar_volume_legacy_alias() -> None:
    rs = {"min_avg_dollar_volume_30d_usd": 25_000_000}
    assert stock_rs_min_daily_dollar_volume(rs) == 25_000_000.0


def test_normalize_stock_rs_migrates_legacy_key(tmp_path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "weights:\n  week: 1\n  month: 0\n  quarter: 0\n  half: 0\n  year: 0\n"
        "stock_rs:\n  min_avg_dollar_volume_30d_usd: 42000000\n",
        encoding="utf-8",
    )
    config = load_config(cfg_path, init_logging=False)
    assert config["stock_rs"]["min_daily_dollar_volume_usd"] == 42_000_000
    assert "min_avg_dollar_volume_30d_usd" not in config["stock_rs"]

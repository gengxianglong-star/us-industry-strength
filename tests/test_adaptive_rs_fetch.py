from src.stock_rs import (
    _adaptive_should_stop,
    _resolve_adaptive_cfg,
    _retryable_symbols,
)


def test_retryable_symbols_filters_reasons():
    issues = {
        "AAA": "no_bars",
        "BBB": "insufficient_history",
        "CCC": "perf_invalid",
        "DDD": "no_bars",
    }
    assert _retryable_symbols(issues) == ["AAA", "CCC", "DDD"]
    assert _retryable_symbols(issues, symbol_set={"AAA", "BBB"}) == ["AAA"]


def test_adaptive_should_stop_on_stall():
    stop, reason = _adaptive_should_stop(
        pass_num=3,
        max_passes=5,
        recovered=0,
        stall_passes=2,
        min_recovered=20,
        at_final_tier=False,
        final_single_complete=False,
        retryable_remaining=100,
        stall_passes_to_stop=2,
    )
    assert stop is True
    assert reason == "stall"


def test_adaptive_should_stop_on_min_recovered_at_final_tier():
    stop, reason = _adaptive_should_stop(
        pass_num=4,
        max_passes=5,
        recovered=5,
        stall_passes=0,
        min_recovered=20,
        at_final_tier=True,
        final_single_complete=True,
        retryable_remaining=50,
        stall_passes_to_stop=2,
    )
    assert stop is True
    assert reason == "min_recovered"


def test_adaptive_should_continue_when_recovering():
    stop, reason = _adaptive_should_stop(
        pass_num=2,
        max_passes=5,
        recovered=120,
        stall_passes=0,
        min_recovered=20,
        at_final_tier=False,
        final_single_complete=False,
        retryable_remaining=800,
        stall_passes_to_stop=2,
    )
    assert stop is False
    assert reason == ""


def test_resolve_adaptive_cfg_defaults_enabled():
    cfg = _resolve_adaptive_cfg({})
    assert cfg["enabled"] is True
    assert cfg["worker_schedule"] == [10, 6, 3, 1]
    assert cfg["batch_size_schedule"] == [40, 20, 10, 5]

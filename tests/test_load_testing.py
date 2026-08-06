from pathlib import Path

import pytest

from parking_chatbot.load_testing.__main__ import main
from parking_chatbot.load_testing.metrics import ScenarioMetrics
from parking_chatbot.load_testing.scenarios import (
    run_administrator_scenario,
    run_chatbot_scenario,
    run_end_to_end_scenario,
    run_mcp_storage_scenario,
)


def test_metrics_calculate_counts_and_latency_statistics() -> None:
    metrics = ScenarioMetrics.calculate(
        "test",
        [0.1, 0.2, 0.3, 0.4],
        [True, False, True, True],
        elapsed_seconds=0.5,
    )

    assert metrics.total_operations == 4
    assert metrics.successful_operations == 3
    assert metrics.failed_operations == 1
    assert metrics.total_elapsed_seconds == 0.5
    assert metrics.throughput_operations_per_second == 8.0
    assert metrics.mean_latency_seconds == pytest.approx(0.25)
    assert metrics.median_latency_seconds == pytest.approx(0.25)
    assert metrics.p95_latency_seconds == 0.4


def test_metrics_reject_invalid_samples() -> None:
    with pytest.raises(ValueError):
        ScenarioMetrics.calculate("empty", [], [], 1.0)
    with pytest.raises(ValueError):
        ScenarioMetrics.calculate("mismatch", [0.1], [], 1.0)


def assert_successful(metrics: ScenarioMetrics, operations: int) -> None:
    assert metrics.total_operations == operations
    assert metrics.successful_operations == operations
    assert metrics.failed_operations == 0
    assert metrics.total_elapsed_seconds >= 0
    assert metrics.mean_latency_seconds >= 0
    assert metrics.median_latency_seconds >= 0
    assert metrics.p95_latency_seconds >= 0


def test_chatbot_load_scenario_keeps_threads_isolated() -> None:
    metrics = run_chatbot_scenario(operations=8, workers=4)

    assert metrics.scenario == "Chatbot"
    assert_successful(metrics, 8)


def test_administrator_load_scenario_handles_independent_requests() -> None:
    metrics = run_administrator_scenario(operations=8, workers=4)

    assert metrics.scenario == "Administrator"
    assert_successful(metrics, 8)


def test_mcp_storage_scenario_is_concurrent_and_idempotent(tmp_path: Path) -> None:
    output_path = tmp_path / "confirmed.txt"

    metrics = run_mcp_storage_scenario(
        operations=8,
        workers=4,
        output_path=output_path,
    )

    assert metrics.scenario == "MCP Storage"
    assert_successful(metrics, 8)
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 8
    assert (
        output_path.resolve()
        != Path("data/dynamic/confirmed_reservations.txt").resolve()
    )


def test_end_to_end_scenario_runs_real_graph_and_records_once(tmp_path: Path) -> None:
    output_path = tmp_path / "orchestrated.txt"

    metrics = run_end_to_end_scenario(
        operations=8,
        workers=4,
        output_path=output_path,
    )

    assert metrics.scenario == "End-to-End"
    assert_successful(metrics, 8)
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 8
    assert len(set(lines)) == 8


def test_benchmark_command_prints_compact_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--operations", "2", "--workers", "2"])

    output = capsys.readouterr().out
    assert "Scenario" in output
    assert "Chatbot" in output
    assert "Administrator" in output
    assert "MCP Storage" in output
    assert "End-to-End" in output

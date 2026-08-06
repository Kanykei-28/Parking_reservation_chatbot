from dataclasses import dataclass
from statistics import mean, median


@dataclass(frozen=True)
class ScenarioMetrics:
    scenario: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    total_elapsed_seconds: float
    throughput_operations_per_second: float
    mean_latency_seconds: float
    median_latency_seconds: float
    p95_latency_seconds: float

    @classmethod
    def calculate(
        cls,
        scenario: str,
        latencies: list[float],
        successes: list[bool],
        elapsed_seconds: float,
    ) -> "ScenarioMetrics":
        if len(latencies) != len(successes):
            raise ValueError("latencies and outcomes must have equal lengths")
        if not latencies:
            raise ValueError("at least one operation is required")
        ordered = sorted(latencies)
        p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
        successful = sum(successes)
        total = len(successes)
        return cls(
            scenario=scenario,
            total_operations=total,
            successful_operations=successful,
            failed_operations=total - successful,
            total_elapsed_seconds=elapsed_seconds,
            throughput_operations_per_second=(
                total / elapsed_seconds if elapsed_seconds > 0 else 0.0
            ),
            mean_latency_seconds=mean(latencies),
            median_latency_seconds=median(latencies),
            p95_latency_seconds=ordered[p95_index],
        )

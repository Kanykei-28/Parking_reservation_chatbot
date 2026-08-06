import argparse
from collections.abc import Sequence

from parking_chatbot.load_testing.scenarios import run_all_scenarios


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Stage 4 load scenarios.")
    parser.add_argument("--operations", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    metrics = run_all_scenarios(args.operations, args.workers)
    print(
        f"{'Scenario':<16} {'Requests':>8} {'Success':>8} {'Failed':>7} "
        f"{'Mean ms':>9} {'P95 ms':>9} {'Ops/s':>9}"
    )
    for result in metrics:
        print(
            f"{result.scenario:<16} {result.total_operations:>8} "
            f"{result.successful_operations:>8} {result.failed_operations:>7} "
            f"{result.mean_latency_seconds * 1000:>9.2f} "
            f"{result.p95_latency_seconds * 1000:>9.2f} "
            f"{result.throughput_operations_per_second:>9.2f}"
        )


if __name__ == "__main__":
    main()

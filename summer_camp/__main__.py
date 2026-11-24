"""Run an accelerated headless scenario and print its event history."""

import argparse
from collections import Counter

from .clock import DAY
from .simulation import MAX_DAYS, Scenario, Simulation
from .world import Request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, MAX_DAYS + 1), default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument(
        "--demo-failure", action="store_true",
        help="try an invalid meal request at the commons before autonomous decisions",
    )
    args = parser.parse_args()
    run = Simulation(Scenario(days=args.days), seed=args.seed)
    if args.demo_failure:
        run.submit("Ada", Request("meal"))
    run.advance(args.days * DAY)
    if not args.summary_only:
        for event in run.history:
            day, remainder = divmod(event.at, DAY)
            hour, remainder = divmod(remainder, 3600)
            minute, second = divmod(remainder, 60)
            detail = f" ({event.detail})" if event.detail else ""
            print(f"Day {day + 1} {hour:02}:{minute:02}:{second:02}  "
                  f"{event.staff:<6} {event.phase:<11} {event.action}{detail}")
    totals = Counter(event.action for event in run.history if event.phase == "completed")
    state = run.snapshot()
    print(f"{run.now // DAY} simulated day(s), {len(run.history)} events")
    print("Completed: " + ", ".join(f"{kind}={count}" for kind, count in sorted(totals.items())))
    repairs = sum(condition == "repaired" for condition in state["repair_states"].values())
    print(f"Servings left: {state['servings']} | Repaired targets: {repairs}")


if __name__ == "__main__":
    main()

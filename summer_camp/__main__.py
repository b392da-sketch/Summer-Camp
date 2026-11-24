"""Run an accelerated headless scenario and print its event history."""

import argparse
from functools import partial
from collections import Counter

from .clock import DAY
from .reference_camp import ecology_camp, maintenance_camp, perception_camp, reference_camp, social_camp, witness_camp
from .simulation import MAX_DAYS, Scenario, Simulation
from .world import Request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("m0", "m1", "m2", "m3", "m4", "m5", "m6"), default="m0")
    parser.add_argument("--days", type=int, choices=range(1, MAX_DAYS + 1))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument(
        "--demo-failure", action="store_true",
        help="try an invalid meal request at the commons before autonomous decisions",
    )
    args = parser.parse_args()
    is_camp = args.scenario != "m0"
    if is_camp and args.demo_failure:
        parser.error("--demo-failure is only available for M0")
    scenarios = {"m0": partial(Scenario, days=args.days or 1),
                 "m1": partial(reference_camp, args.days or 4),
                 "m2": partial(social_camp, args.days or 4),
                 "m3": partial(perception_camp, args.days or 4),
                 "m4": partial(witness_camp, args.days or 4),
                 "m5": partial(ecology_camp, args.days or 4),
                 "m6": partial(maintenance_camp, args.days or 4)}
    scenario = scenarios[args.scenario]()
    run = Simulation(scenario, seed=args.seed)
    if args.demo_failure:
        run.submit("Ada", Request("meal"))
    run.advance(scenario.days * DAY)
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
    if is_camp:
        print(f"Servings left: {state['servings']} | Ingredients left: {state['ingredients']}")
        outcomes = Counter(state["job_states"].values())
        print("Jobs: " + ", ".join(f"{condition}={count}" for condition, count in sorted(outcomes.items())))
        counts = Counter((event.staff, event.action) for event in run.history if event.phase == "completed")
        for staff in scenario.staff:
            kinds = ("sleep", "meal", "leisure", "prepare")
            metrics = ", ".join(f"{kind}={counts[staff.name, kind]}" for kind in kinds)
            print(f"{staff.name} ({staff.profile.role}): {metrics}")
    else:
        repairs = sum(condition == "repaired" for condition in state["repair_states"].values())
        print(f"Servings left: {state['servings']} | Repaired targets: {repairs}")


if __name__ == "__main__":
    main()

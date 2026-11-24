"""Staff decisions use private needs, commitments, and perceived facts."""

from collections import deque
from dataclasses import dataclass, field
from random import Random

from .world import ACTIVITIES, MINUTE, PATHS, Observation, RepairCommitment, Request

REASSESS = 15 * MINUTE
MEMORY_WINDOW = 60 * MINUTE
HUNGER_INTERRUPT = 75
GROWTH = {"meal": 8, "rest": 4, "work": 3, "leisure": 4}
RELIEF = {"meal": 80, "rest": 85, "work": 75, "leisure": 65}


@dataclass(frozen=True)
class Staff:
    name: str
    location: str = "commons"
    # Order follows ACTIVITIES: meal, rest, work, leisure.
    needs: tuple[int, int, int, int] | None = None
    preferences: tuple[int, int, int, int] | None = None


@dataclass
class Mind:
    needs: dict[str, int]
    preferences: dict[str, int]
    memory: dict[str, Observation] = field(default_factory=dict)
    repair_commitment: RepairCommitment | None = None
    travel_goal: str | None = None
    last_update: int = 0

    @classmethod
    def create(cls, staff: Staff, rng: Random) -> "Mind":
        needs = staff.needs
        if needs is None:
            needs = tuple(rng.randrange(15, 66) for _ in ACTIVITIES)
        preferences = staff.preferences
        if preferences is None:
            preferences = tuple(rng.randrange(-8, 9) for _ in ACTIVITIES)
        if len(needs) != len(ACTIVITIES) or any(
            type(value) is not int or not 0 <= value <= 100 for value in needs
        ):
            raise ValueError("Staff needs must contain four integers from 0 to 100")
        if len(preferences) != len(ACTIVITIES) or any(type(value) is not int for value in preferences):
            raise ValueError("Staff preferences must contain four integers")
        # Store points multiplied by REASSESS to keep fractional accrual exact.
        return cls(
            dict(zip(ACTIVITIES, (value * REASSESS for value in needs))),
            dict(zip(ACTIVITIES, preferences)),
        )

    def accrue(self, now: int) -> None:
        elapsed = now - self.last_update
        for kind, growth in GROWTH.items():
            self.needs[kind] = min(100 * REASSESS, self.needs[kind] + elapsed * growth)
        self.last_update = now

    def satisfy(self, kind: str) -> None:
        self.needs[kind] = max(0, self.needs[kind] - RELIEF[kind] * REASSESS)

    def wants_meal_break(self, now: int) -> bool:
        return self.needs["meal"] >= HUNGER_INTERRUPT * REASSESS and self._available("meal", now)

    def _available(self, kind: str, now: int) -> bool:
        seen = self.memory.get(kind)
        if seen is None:
            return True
        # A fully repaired workshop stays that way in M0.
        if kind == "work" and not seen.damaged_targets:
            return False
        if now - seen.at >= MEMORY_WINDOW:
            return True
        if seen.servings == 0:
            return False
        # A busy resource elsewhere is a short-lived signal. Local observations
        # are refreshed before choosing and take precedence over old memories.
        return seen.free > 0 or now - seen.at >= REASSESS

    def choose(self, location: str, now: int) -> tuple[str, Request] | None:
        if self.wants_meal_break(now):
            return "meal", self.request_for("meal", location)
        if self.travel_goal is not None and self._available(self.travel_goal, now):
            return self.travel_goal, self.request_for(self.travel_goal, location)

        candidates = []
        for kind, activity in ACTIVITIES.items():
            if not self._available(kind, now):
                continue
            steps = route(location, activity.location)
            score = self.needs[kind] // REASSESS + self.preferences[kind] - 6 * len(steps)
            if kind == "work" and self.repair_commitment is not None:
                score += 25
            if activity.location == location or score >= 15:
                candidates.append((score, kind, steps))
        if not candidates:
            return None
        _, kind, steps = max(candidates, key=lambda candidate: candidate[0])
        return kind, self._request(kind, steps)

    def request_for(self, kind: str, location: str) -> Request:
        steps = route(location, ACTIVITIES[kind].location)
        return self._request(kind, steps)

    def _request(self, kind: str, steps: tuple[str, ...]) -> Request:
        if steps:
            return Request("move", steps[0])
        if kind == "work":
            targets = self.memory["work"].damaged_targets
            commitment = self.repair_commitment
            target = commitment.target if commitment is not None else targets[0]
            return Request("work", target=target)
        return Request(kind)


def route(origin: str, destination: str) -> tuple[str, ...]:
    pending = deque([(origin, ())])
    visited = {origin}
    while pending:
        current, steps = pending.popleft()
        if current == destination:
            return steps
        for neighbor in PATHS[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append((neighbor, (*steps, neighbor)))
    raise ValueError("Disconnected camp map")

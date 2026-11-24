"""Staff decisions use private needs, commitments, and perceived facts."""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from random import Random

from .clock import DAY
from .world import ACTIVITIES, MINUTE, PATHS, Observation, RepairCommitment, Request

REASSESS = 15 * MINUTE
MEMORY_WINDOW = 60 * MINUTE
HUNGER_INTERRUPT = 75
GROWTH = {"meal": 8, "rest": 4, "work": 3, "leisure": 4}
RELIEF = {"meal": 80, "rest": 85, "work": 75, "leisure": 65}


HOUR = 60 * MINUTE
RETRY = 2 * HOUR
CAMP_GROWTH = {"meal": 9, "rest": 4, "work": 2, "leisure": 5}


@dataclass(frozen=True)
class StaffProfile:
    role: str
    responsibilities: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    bedtime: int = 22 * HOUR
    sleep_duration: int = 8 * HOUR

    def __post_init__(self):
        if (type(self.bedtime) is not int or not 0 <= self.bedtime < DAY
                or type(self.sleep_duration) is not int or self.sleep_duration <= 0):
            raise ValueError("Invalid sleep timing")


@dataclass(frozen=True)
class Staff:
    name: str
    location: str = "commons"
    # Order follows ACTIVITIES: meal, rest, work, leisure.
    needs: tuple[int, int, int, int] | None = None
    preferences: tuple[int, int, int, int] | None = None
    profile: StaffProfile | None = None


@dataclass
class Mind:
    needs: dict[str, int]
    preferences: dict[str, int]
    memory: dict[str, Observation] = field(default_factory=dict)
    repair_commitment: RepairCommitment | None = None
    travel_goal: str | None = None
    last_update: int = 0
    profile: StaffProfile | None = None
    preparations: dict[str, RepairCommitment] = field(default_factory=dict)

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
        scale = HOUR if staff.profile is not None else REASSESS
        return cls(
            dict(zip(ACTIVITIES, (value * scale for value in needs))),
            dict(zip(ACTIVITIES, preferences)),
            profile=staff.profile,
        )

    def accrue(self, now: int, *, sleeping: bool = False) -> None:
        elapsed = now - self.last_update
        if self.profile is not None:
            for kind, rate in CAMP_GROWTH.items():
                if kind == "rest" and sleeping:
                    rate = -12
                elif kind == "meal" and sleeping:
                    rate = 2
                points = self.needs[kind] + elapsed * rate
                self.needs[kind] = min(100 * HOUR, max(0, points))
            self.last_update = now
            return
        for kind, growth in GROWTH.items():
            self.needs[kind] = min(100 * REASSESS, self.needs[kind] + elapsed * growth)
        self.last_update = now

    def satisfy(self, kind: str) -> None:
        if self.profile is not None:
            relief = {"meal": 75, "prepare": 70, "leisure": 55}
            if kind in relief:
                need = "work" if kind == "prepare" else kind
                self.needs[need] = max(0, self.needs[need] - relief[kind] * HOUR)
            return
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

    def camp_break(self, now: int, location: str) -> str | None:
        if self.needs["rest"] >= 90 * HOUR:
            return "fatigue"
        if self.needs["meal"] >= 82 * HOUR and self.camp_available("meal", now, location):
            return "hunger"
        return None

    def camp_available(self, kind: str, now: int, location: str) -> bool:
        seen = self.memory.get(kind)
        if seen is None:
            return True
        facility = CAMP_DESTINATIONS[kind]
        if location != facility and now - seen.at >= RETRY:
            return True
        return seen.free > 0 and seen.servings != 0

    def choose_camp(
        self, location: str, now: int, paths: Mapping[str, tuple[str, ...]],
        help_intent: tuple[str, Request] | None = None,
        seek_company: bool = False,
    ) -> tuple[str, Request] | None:
        profile = self.profile
        assert profile is not None
        points = {kind: value // HOUR for kind, value in self.needs.items()}
        bedtime_distance = abs((now - profile.bedtime + DAY // 2) % DAY - DAY // 2)
        sleep_threshold = min(90, 50 + bedtime_distance * 6 // HOUR)
        sleep_bonus = max(0, 28 - bedtime_distance * 6 // HOUR)
        meal_window = any(0 <= now % DAY - hour * HOUR < 2 * HOUR for hour in (7, 12, 18))
        candidates: list[tuple[int, str, Request]] = []

        def offer(score: int, goal: str, destination: str, request: Request | None = None):
            steps = route(location, destination, paths)
            if steps:
                request = Request("move", steps[0])
            if request is None:
                return
            if self.travel_goal == goal:
                score += 12
            candidates.append((score - 6 * len(steps), goal, request))

        if points["rest"] >= sleep_threshold and self.camp_available("sleep", now, location):
            offer(points["rest"] + self.preferences["rest"] + sleep_bonus,
                  "sleep", "cabins", Request("sleep"))
        if points["meal"] >= 42 and self.camp_available("meal", now, location):
            offer(points["meal"] + self.preferences["meal"] + (12 if meal_window else 0)
                  + (32 if points["meal"] >= 82 else 0), "meal", "kitchen", Request("meal"))
        if points["leisure"] >= 25 and self.camp_available("leisure", now, location):
            offer(18 + points["leisure"] // 2 + self.preferences["leisure"],
                  "leisure", "commons", Request("leisure"))

        if seek_company and location != "commons":
            offer(26, "company", "commons", Request("leisure"))

        if help_intent is not None:
            destination, request = help_intent
            offer(65, f"prepare:{destination}", destination, request)

        for facility in paths:
            goal = f"prepare:{facility}"
            observed = self.memory.get(goal)
            responsible = facility in profile.responsibilities
            if observed is None:
                if responsible:
                    offer(43, goal, facility)
                continue
            eligible = [
                job for job in observed.jobs if not job.done and job.capability in profile.capabilities
            ]
            if not eligible:
                continue
            fresh = facility == location or now - observed.at < RETRY
            for job in eligible:
                if not job.available and fresh:
                    continue
                committed = job.target in self.preparations
                score = 27 + points["work"] // 3 + self.preferences["work"]
                score += 15 if responsible else 0
                score += 18 if committed else 0
                if job.category == "cook":
                    meals = self.memory.get("meal")
                    if meals is not None and meals.servings is not None:
                        if meals.servings < 8:
                            score += 16
                        elif meals.servings >= 20:
                            score -= 45
                if score < 25:
                    continue
                offer(score, goal, facility, Request("prepare", target=job.target))

        if not candidates:
            return None
        _, goal, request = max(candidates, key=lambda candidate: candidate[0])
        return goal, request


CAMP_DESTINATIONS = {"meal": "kitchen", "sleep": "cabins", "leisure": "commons"}


def route(
    origin: str, destination: str, paths: Mapping[str, tuple[str, ...]] = PATHS,
) -> tuple[str, ...]:
    pending = deque([(origin, ())])
    visited = {origin}
    while pending:
        current, steps = pending.popleft()
        if current == destination:
            return steps
        for neighbor in paths[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append((neighbor, (*steps, neighbor)))
    raise ValueError("Disconnected camp map")

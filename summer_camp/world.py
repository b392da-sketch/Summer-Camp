"""Physical state, action requests, and their resolution."""

from dataclasses import dataclass
from types import MappingProxyType

MINUTE = 60

# The layout is posted at the camp. Live occupancy and supplies are private
# to the world until a staff member visits the relevant location.
PATHS = MappingProxyType({
    "commons": ("cabins", "kitchen", "workshop"),
    "cabins": ("commons",),
    "kitchen": ("commons",),
    "workshop": ("commons",),
})


@dataclass(frozen=True)
class Activity:
    location: str
    duration: int
    capacity: int


ACTIVITIES = MappingProxyType({
    "meal": Activity("kitchen", 25 * MINUTE, 2),
    "rest": Activity("cabins", 120 * MINUTE, 2),
    "work": Activity("workshop", 100 * MINUTE, 1),
    "leisure": Activity("commons", 45 * MINUTE, 4),
})


@dataclass(frozen=True)
class Request:
    kind: str
    destination: str | None = None


@dataclass(frozen=True)
class Observation:
    at: int
    free: int
    servings: int | None = None
    repairs: int | None = None


@dataclass(frozen=True)
class Action:
    request: Request
    ends_at: int


class World:
    def __init__(self, starting_locations: dict[str, str], servings: int):
        self.locations = dict(starting_locations)
        self.servings = servings
        self.repairs = 0
        self.active: dict[str, Action] = {}

    def observe(self, staff: str, now: int) -> dict[str, Observation]:
        if staff in self.active and self.active[staff].request.kind == "move":
            return {}
        return {
            kind: Observation(
                now, self.free_slots(kind),
                self.servings if kind == "meal" else None,
                self.repairs if kind == "work" else None,
            )
            for kind, activity in ACTIVITIES.items()
            if self.locations[staff] == activity.location
        }

    def free_slots(self, kind: str) -> int:
        occupied = sum(action.request.kind == kind for action in self.active.values())
        return ACTIVITIES[kind].capacity - occupied

    def start(
        self, staff: str, request: Request, now: int, work_remaining: int | None
    ) -> Action:
        if staff in self.active:
            raise ValueError("already occupied")
        kind = request.kind
        location = self.locations[staff]
        if kind == "move":
            if request.destination not in PATHS[location]:
                raise ValueError("destination is not adjacent")
            duration = 10 * MINUTE
        else:
            if kind not in ACTIVITIES or request.destination is not None:
                raise ValueError("unknown or malformed activity")
            activity = ACTIVITIES[kind]
            if activity.location != location:
                raise ValueError("wrong location")
            if self.free_slots(kind) == 0:
                raise ValueError("resource occupied")
            if kind == "meal" and self.servings == 0:
                raise ValueError("no servings available")
            duration = work_remaining if kind == "work" and work_remaining else activity.duration

        action = Action(request, now + duration)
        self.active[staff] = action
        if kind == "meal":
            self.servings -= 1
        return action

    def finish(self, staff: str) -> str:
        kind = self.active[staff].request.kind
        detail = ""
        if kind == "move":
            destination = self.active[staff].request.destination
            assert destination is not None
            self.locations[staff] = destination
            detail = destination
        elif kind == "work":
            self.repairs += 1
            detail = f"repairs={self.repairs}"
        del self.active[staff]
        return detail

    def interrupt_work(self, staff: str, now: int) -> int:
        action = self.active[staff]
        assert action.request.kind == "work" and now < action.ends_at
        del self.active[staff]
        return action.ends_at - now

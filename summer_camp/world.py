"""Physical state, action requests, and their resolution."""

from collections.abc import Mapping
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
    target: str | None = None


@dataclass(frozen=True)
class Job:
    target: str
    category: str
    location: str
    duration: int
    capability: str
    ingredients: int = 0
    produces: int = 0

    def __post_init__(self):
        if not self.target or not self.capability or type(self.duration) is not int or self.duration <= 0:
            raise ValueError("A job needs an identity, a capability and a positive duration")
        if self.category == "cook":
            if self.location != "kitchen":
                raise ValueError("Cooking jobs belong in the kitchen")
            if any(type(quantity) is not int or quantity <= 0
                   for quantity in (self.ingredients, self.produces)):
                raise ValueError("Cooking needs positive ingredient and serving quantities")
        elif self.category not in ("repair", "cabin") or self.ingredients or self.produces:
            raise ValueError("Invalid preparation job")


@dataclass(frozen=True)
class JobOffer:
    target: str
    category: str
    capability: str
    done: bool
    available: bool


@dataclass(frozen=True)
class Observation:
    at: int
    free: int
    servings: int | None = None
    damaged_targets: tuple[str, ...] = ()
    jobs: tuple[JobOffer, ...] = ()


@dataclass(frozen=True)
class RepairCommitment:
    target: str
    remaining: int


@dataclass(frozen=True)
class Action:
    request: Request
    ends_at: int


class World:
    def __init__(
        self, starting_locations: dict[str, str], servings: int, repair_targets: tuple[str, ...],
        *, paths: Mapping[str, tuple[str, ...]] = PATHS, jobs: tuple[Job, ...] = (),
        ingredients: int = 0, capabilities: Mapping[str, tuple[str, ...]] | None = None,
        sleep_durations: Mapping[str, int] | None = None,
    ):
        self.locations = dict(starting_locations)
        self.servings = servings
        self.repair_states = dict.fromkeys(repair_targets, "damaged")
        self.active: dict[str, Action] = {}
        self.paths = paths
        self.jobs = {job.target: job for job in jobs}
        self.job_states = dict.fromkeys(self.jobs, "pending")
        self.ingredients = ingredients
        self.capabilities = capabilities or {}
        self.sleep_durations = sleep_durations or {}
        self.activities = ACTIVITIES
        if sleep_durations is not None:
            self.activities = {
                "meal": Activity("kitchen", 25 * MINUTE, 6),
                "sleep": Activity("cabins", 0, len(starting_locations)),
                "leisure": Activity("commons", 55 * MINUTE, len(starting_locations)),
            }


    def observe(self, staff: str, now: int) -> dict[str, Observation]:
        if staff in self.active and self.active[staff].request.kind in ("move", "sleep"):
            return {}
        observations = {
            kind: Observation(
                now, self.free_slots(kind),
                self.servings if kind == "meal" else None,
                tuple(target for target, state in self.repair_states.items() if state == "damaged")
                if kind == "work" else (),
            )
            for kind, activity in self.activities.items()
            if self.locations[staff] == activity.location
        }

        if staff in self.sleep_durations:
            location = self.locations[staff]
            free = self.preparation_free(location)
            ingredients = self.unreserved_ingredients
            observations[f"prepare:{location}"] = Observation(
                now, int(free), jobs=tuple(
                    JobOffer(job.target, job.category, job.capability,
                             self.job_states[job.target] != "pending",
                             free and self.job_states[job.target] == "pending"
                             and job.ingredients <= ingredients)
                    for job in self.jobs.values() if job.location == location
                ),
            )
        return observations

    @property
    def unreserved_ingredients(self) -> int:
        return self.ingredients - sum(
            self.jobs[action.request.target].ingredients
            for action in self.active.values() if action.request.kind == "prepare"
        )

    def preparation_free(self, location: str) -> bool:
        return all(
            action.request.kind != "prepare" or self.jobs[action.request.target].location != location
            for action in self.active.values()
        )

    def free_slots(self, kind: str) -> int:
        occupied = sum(action.request.kind == kind for action in self.active.values())
        return self.activities[kind].capacity - occupied

    def start(
        self, staff: str, request: Request, now: int, commitment: RepairCommitment | None
    ) -> Action:
        if staff in self.active:
            raise ValueError("already occupied")
        kind = request.kind
        location = self.locations[staff]
        if kind not in ("work", "prepare") and request.target is not None:
            raise ValueError("unexpected repair target")
        if kind == "move":
            if request.destination not in self.paths[location]:
                raise ValueError("destination is not adjacent")
            duration = 10 * MINUTE
        elif kind == "prepare":
            if request.destination is not None:
                raise ValueError("malformed preparation request")
            job = self.jobs.get(request.target)
            if job is None or self.job_states[job.target] != "pending":
                raise ValueError("job unavailable")
            if location != job.location:
                raise ValueError("wrong location")
            if job.capability not in self.capabilities.get(staff, ()):
                raise ValueError("missing capability")
            if not self.preparation_free(location):
                raise ValueError("equipment occupied")
            if job.ingredients > self.unreserved_ingredients:
                raise ValueError("insufficient unreserved ingredients")
            duration = job.duration
            if commitment is not None and commitment.target == job.target:
                duration = commitment.remaining
        else:
            if kind not in self.activities or request.destination is not None:
                raise ValueError("unknown or malformed activity")
            activity = self.activities[kind]
            if activity.location != location:
                raise ValueError("wrong location")
            if self.free_slots(kind) == 0:
                raise ValueError("resource occupied")
            if kind == "meal" and self.servings == 0:
                raise ValueError("no servings available")
            duration = self.sleep_durations[staff] if kind == "sleep" else activity.duration
            if kind == "work":
                if self.repair_states.get(request.target) != "damaged":
                    raise ValueError("repair target is unavailable")
                if commitment is not None and commitment.target == request.target:
                    duration = commitment.remaining

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
        elif kind == "prepare":
            job = self.jobs[self.active[staff].request.target]
            assert self.job_states[job.target] == "pending" and self.ingredients >= job.ingredients
            self.ingredients -= job.ingredients
            self.servings += job.produces
            outcome = {"cook": "cooked", "repair": "repaired", "cabin": "ready"}[job.category]
            self.job_states[job.target] = outcome
            detail = f"target={job.target} pending -> {outcome}"
            if job.produces:
                detail += f", ingredients -{job.ingredients}, servings +{job.produces}"
        elif kind == "work":
            target = self.active[staff].request.target
            assert target is not None and self.repair_states[target] == "damaged"
            self.repair_states[target] = "repaired"
            detail = f"target={target} damaged -> repaired"
        del self.active[staff]
        return detail

    def interrupt_work(self, staff: str, now: int) -> RepairCommitment:
        action = self.active[staff]
        assert action.request.kind in ("work", "prepare") and now < action.ends_at
        del self.active[staff]
        target = action.request.target
        assert target is not None
        return RepairCommitment(target, action.ends_at - now)

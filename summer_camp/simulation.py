"""Coordinate the clock, private decisions, world transitions, and history."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import partial
from random import Random
from types import MappingProxyType

from .clock import DAY, Clock
from .cognition import CAMP_DESTINATIONS, REASSESS, Mind, Staff, route
from .world import PATHS, Action, Job, Observation, Request, World

MAX_DAYS = 7
DEFAULT_REPAIRS = ("canoe rack", "supply cart", "trail sign")
DEFAULT_STAFF = (Staff("Ada"), Staff("Ben"), Staff("Clara"))


@dataclass(frozen=True)
class CampLayout:
    paths: Mapping[str, tuple[str, ...]]
    jobs: tuple[Job, ...]
    ingredients: int

    def __post_init__(self):
        paths = {location: tuple(neighbors) for location, neighbors in self.paths.items()}
        if type(self.ingredients) is not int or self.ingredients < 0:
            raise ValueError("Ingredients must be a nonnegative integer")
        if any(location not in paths for location in CAMP_DESTINATIONS.values()):
            raise ValueError("Camp needs cabins, a kitchen and commons")
        for location, neighbors in paths.items():
            if any(location not in paths.get(neighbor, ()) for neighbor in neighbors):
                raise ValueError("Camp paths must connect known facilities in both directions")
            route("commons", location, paths)
        if len({job.target for job in self.jobs}) != len(self.jobs):
            raise ValueError("Job identities must be unique")
        if any(job.location not in paths for job in self.jobs):
            raise ValueError("Jobs must use known facilities")
        object.__setattr__(self, "paths", MappingProxyType(paths))


@dataclass(frozen=True)
class Scenario:
    staff: tuple[Staff, ...] = DEFAULT_STAFF
    days: int = MAX_DAYS
    servings: int = 200
    repair_targets: tuple[str, ...] = DEFAULT_REPAIRS
    camp: CampLayout | None = None

    def __post_init__(self):
        if type(self.days) is not int or not 1 <= self.days <= MAX_DAYS:
            raise ValueError("Scenario duration must be one to seven whole days")
        if type(self.servings) is not int or self.servings < 0:
            raise ValueError("Servings must be a nonnegative integer")
        if any(not target for target in self.repair_targets):
            raise ValueError("Repair targets must be named")
        if len(self.repair_targets) != len(set(self.repair_targets)):
            raise ValueError("Repair target names must be unique")
        names = [staff.name for staff in self.staff]
        if not names or any(not name for name in names) or len(names) != len(set(names)):
            raise ValueError("Staff names must be nonempty and unique")
        paths = self.camp.paths if self.camp is not None else PATHS
        if any((staff.profile is not None) != (self.camp is not None) for staff in self.staff):
            raise ValueError("Camp scenarios require a profile for every staff member")
        for staff in self.staff:
            if staff.profile is not None and any(
                location not in paths for location in staff.profile.responsibilities
            ):
                raise ValueError("Responsibilities must use known facilities")
        if any(staff.location not in paths for staff in self.staff):
            raise ValueError("Staff must start at a camp location")


@dataclass(frozen=True)
class Event:
    at: int
    staff: str
    phase: str
    action: str
    detail: str = ""


class Simulation:
    def __init__(self, scenario: Scenario = Scenario(), *, seed: int = 0):
        self.horizon = scenario.days * DAY
        self._clock = Clock()
        rng = Random(seed)
        self._minds = {staff.name: Mind.create(staff, rng) for staff in scenario.staff}
        camp = scenario.camp
        self._world = World(
            {staff.name: staff.location for staff in scenario.staff},
            scenario.servings,
            scenario.repair_targets if camp is None else (),
            paths=camp.paths if camp is not None else PATHS,
            jobs=camp.jobs if camp is not None else (),
            ingredients=camp.ingredients if camp is not None else 0,
            capabilities={staff.name: staff.profile.capabilities for staff in scenario.staff
                          if staff.profile is not None},
            sleep_durations={staff.name: staff.profile.sleep_duration for staff in scenario.staff
                             if staff.profile is not None} if camp is not None else None,
        )
        self._history: list[Event] = []
        self._wakes: dict[str, tuple[int, int]] = {}
        self._wake_sequence = 0
        for staff in self._minds:
            self._schedule(staff, 0)

    @property
    def now(self) -> int:
        return self._clock.now

    @property
    def history(self) -> tuple[Event, ...]:
        return tuple(self._history)

    def advance(self, seconds: int) -> int:
        if type(seconds) is not int or seconds < 0:
            raise ValueError("Advance by a nonnegative integer number of seconds")
        return self._clock.advance(min(seconds, self.horizon - self.now))

    def submit(self, staff: str, request: Request) -> bool:
        """Try an immediate external input at the current simulated timestamp."""
        if staff not in self._minds:
            raise ValueError(f"Unknown staff member: {staff}")
        if self.now == self.horizon:
            self._record(staff, "failed", request.kind, "scenario ended")
            return False
        return self._start(staff, request)

    def snapshot(self) -> dict:
        """Return a detached view of authoritative state for diagnostics."""
        state = {
            "now": self.now,
            "horizon": self.horizon,
            "locations": dict(self._world.locations),
            "servings": self._world.servings,
            "repair_states": dict(self._world.repair_states),
            "active": {staff: asdict(action) for staff, action in self._world.active.items()},
            "minds": {staff: asdict(mind) for staff, mind in self._minds.items()},
            "scheduled": sorted((when, sequence, staff) for staff, (when, sequence) in self._wakes.items()),
        }

        if self._world.sleep_durations:
            state.update(
                job_states=dict(self._world.job_states),
                ingredients=self._world.ingredients,
                reserved_ingredients=self._world.ingredients - self._world.unreserved_ingredients,
            )
        return state

    def cancel_preparation(self, staff: str) -> bool:
        """Cancel an active M1 job, releasing reservations and discarding its progress."""
        action = self._world.active.get(staff)
        if action is None or action.request.kind != "prepare" or self.now == self.horizon:
            return False
        commitment = self._world.interrupt_work(staff, self.now)
        self._record(staff, "cancelled", "prepare", f"target={commitment.target}")
        self._schedule(staff, self.now)
        return True

    def _record(self, staff: str, phase: str, action: str, detail: str = "") -> None:
        self._history.append(Event(self.now, staff, phase, action, detail))

    def _schedule(self, staff: str, when: int) -> None:
        self._wake_sequence += 1
        ticket = (when, self._wake_sequence)
        self._wakes[staff] = ticket
        self._clock.schedule(when, partial(self._wake, staff, ticket))

    def _start(self, staff: str, request: Request, goal: str | None = None) -> bool:
        mind = self._minds[staff]
        commitment = mind.repair_commitment
        if request.kind == "prepare" and request.target is not None:
            commitment = mind.preparations.get(request.target)
        try:
            action = self._world.start(staff, request, self.now, commitment)
        except ValueError as error:
            self._record(staff, "failed", request.kind, str(error))
            return False

        kind = request.kind
        phase = "started"
        detail = ""
        if kind in ("work", "prepare"):
            detail = f"target={request.target}"
            if commitment is not None and request.target == commitment.target:
                phase = "resumed"
        elif kind == "move":
            detail = f"to={request.destination} goal={goal or 'external'}"
        if mind.profile is not None:
            mind.accrue(self.now)
        if kind == "sleep":
            detail = f"duration={action.ends_at - self.now}s"
        self._record(staff, phase, kind, detail)
        mind.travel_goal = goal if kind == "move" else None
        if phase == "resumed":
            if kind == "prepare":
                del mind.preparations[commitment.target]
            else:
                mind.repair_commitment = None
        self._schedule(staff, self._next_check(kind, action.ends_at))
        return True

    def _next_check(self, kind: str, ends_at: int) -> int:
        if kind in ("prepare", "sleep"):
            return min(ends_at, self.now + REASSESS, self.horizon)
        return min(ends_at, self.now + REASSESS) if kind == "work" else ends_at

    def _wake(self, staff: str, ticket: tuple[int, int]) -> None:
        if self._wakes.get(staff) != ticket:
            return
        del self._wakes[staff]
        mind = self._minds[staff]
        action = self._world.active.get(staff)
        sleeping = action is not None and action.request.kind == "sleep"
        mind.accrue(self.now, sleeping=sleeping)
        if action and action.ends_at == self.now:
            kind = action.request.kind
            detail = self._world.finish(staff)
            if kind != "move":
                mind.satisfy(kind)
            self._record(staff, "completed", kind, detail)
            action = None

        observations = self._world.observe(staff, self.now)
        mind.memory.update(observations)
        commitment = mind.repair_commitment
        location = self._world.locations[staff]
        if mind.profile is not None:
            self._camp_wake(staff, mind, action, observations, location)
            return
        if commitment is not None and "work" in observations:
            if commitment.target not in observations["work"].damaged_targets:
                mind.repair_commitment = None
                self._record(staff, "abandoned", "work", f"target={commitment.target} no longer damaged")
        if self.now == self.horizon:
            return
        if action:
            if action.request.kind != "work" or not mind.wants_meal_break(self.now):
                self._schedule(staff, self._next_check(action.request.kind, action.ends_at))
                return
            commitment = self._world.interrupt_work(staff, self.now)
            mind.repair_commitment = commitment
            self._record(staff, "interrupted", "work",
                         f"target={commitment.target}, hunger, {commitment.remaining}s remaining")

        intended = mind.travel_goal
        if intended in observations:
            seen = observations[intended]
            reason = None
            if seen.servings == 0:
                reason = "no servings observed"
            elif intended == "work" and not seen.damaged_targets:
                reason = "no damaged targets observed"
            elif seen.free == 0:
                reason = "resource occupied"
            if reason is not None:
                self._record(staff, "redirected", intended, reason)
                mind.travel_goal = None

        decision = mind.choose(location, self.now)
        if decision is not None:
            goal, request = decision
            if self._start(staff, request, goal):
                return
        mind.travel_goal = None
        self._schedule(staff, self.now + REASSESS)

    def _camp_wake(
        self, staff: str, mind: Mind, action: Action | None,
        observations: dict[str, Observation], location: str,
    ) -> None:
        local_jobs = observations.get(f"prepare:{location}")
        for job in local_jobs.jobs if local_jobs is not None else ():
            if job.done and job.target in mind.preparations:
                del mind.preparations[job.target]
                self._record(staff, "abandoned", "prepare", f"target={job.target} completed by peer")
        if self.now == self.horizon:
            return
        if action is not None:
            kind = action.request.kind
            reason = mind.camp_break(self.now, location) if kind == "prepare" else None
            if reason is None:
                self._schedule(staff, self._next_check(kind, action.ends_at))
                return
            commitment = self._world.interrupt_work(staff, self.now)
            mind.preparations[commitment.target] = commitment
            self._record(staff, "interrupted", kind,
                         f"target={commitment.target}, {reason}, {commitment.remaining}s remaining")

        decision = mind.choose_camp(location, self.now, self._world.paths)
        if decision is not None:
            goal, request = decision
            if self._start(staff, request, goal):
                return
        mind.travel_goal = None
        self._schedule(staff, min(self.now + REASSESS, self.horizon))

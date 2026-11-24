"""Physical state, action requests, and their resolution."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .ecology import Ecology, EcologyState
from .maintenance import (
    HEAVY_WETNESS, RIGHTING_TIME, WET_TRAVEL_TIME, Maintenance, ObsoleteRighting,
    Reservation, RightingProgress,
)
from .perception import INSPECTION_TIME, Environment, Evidence, PhysicalEvent, inspect

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
    fitting: str | None = None

    def __post_init__(self):
        if not self.target or not self.capability or type(self.duration) is not int or self.duration <= 0:
            raise ValueError("A job needs an identity, a capability and a positive duration")
        if (self.category == "secure") != bool(self.fitting):
            raise ValueError("Only securing jobs require a fitting")
        if self.category == "cook":
            if self.location != "kitchen":
                raise ValueError("Cooking jobs belong in the kitchen")
            if any(type(quantity) is not int or quantity <= 0
                   for quantity in (self.ingredients, self.produces)):
                raise ValueError("Cooking needs positive ingredient and serving quantities")
        elif self.category not in ("repair", "cabin", "secure") or self.ingredients or self.produces:
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


@dataclass(frozen=True)
class RightingAction(Action):
    reservation: Reservation


@dataclass(frozen=True)
class RouteAction(Action):
    duration: int


class World:
    def __init__(
        self, starting_locations: dict[str, str], servings: int, repair_targets: tuple[str, ...],
        *, paths: Mapping[str, tuple[str, ...]] = PATHS, jobs: tuple[Job, ...] = (),
        ingredients: int = 0, capabilities: Mapping[str, tuple[str, ...]] | None = None,
        sleep_durations: Mapping[str, int] | None = None,
        environment: Environment | None = None,
        ecology: Ecology | None = None,
        maintenance: Maintenance | None = None,
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
        self.environment = environment
        self.fitting_positions = {item.key: False for item in environment.fittings} if environment else {}
        self.fitting_security = {item.key: not item.loose for item in environment.fittings} if environment else {}
        self.ecology = EcologyState(ecology) if ecology is not None else None
        self.maintenance = maintenance
        self.righting: Reservation | None = None
        self._righting_sequence = 0
        self.activities = ACTIVITIES
        if sleep_durations is not None:
            self.activities = {
                "meal": Activity("kitchen", 25 * MINUTE, 6),
                "sleep": Activity("cabins", 0, len(starting_locations)),
                "leisure": Activity("commons", 55 * MINUTE, len(starting_locations)),
            }


    def disturb(self, target: str, cause: str, now: int) -> PhysicalEvent | None:
        if self.environment is None:
            return None
        for item in self.environment.fittings:
            if item.key == target and not self.fitting_security[target]:
                opened = not self.fitting_positions[target]
                self.fitting_positions[target] = opened
                return PhysicalEvent(now, item, cause, opened)
        return None

    def inspect(self, location: str, now: int) -> tuple[Evidence, ...]:
        environment = self.environment
        assert environment is not None
        findings = inspect(environment, location, now, self.fitting_security)
        if self.ecology is None or environment.light(location, now) + 1 < 3:
            return findings
        ecology = self.ecology
        if location == ecology.config.refuse:
            condition = "tipped container" if ecology.tipped else "upright container"
            findings += (Evidence(now, "inspection", condition, location, "refuse container"),)
        if ecology.wetness.get(location, 0):
            findings += (Evidence(now, "inspection", "wet ground", location, "ground"),)
        return findings

    def notice_container(self, staff: str, now: int) -> Evidence | None:
        if self.maintenance is None:
            return None
        ecology = self.ecology
        environment = self.environment
        assert ecology is not None and environment is not None
        node = self.perceptual_location(staff)
        if node != ecology.config.refuse or environment.light(node, now) - self.is_focused(staff) < 2:
            return None
        condition = "tipped container" if ecology.tipped else "upright container"
        return Evidence(now, "notice", condition, node, "refuse container")

    def perceptual_location(self, staff: str) -> str | None:
        action = self.active.get(staff)
        if action is not None and action.request.kind in ("move", "sleep"):
            return None
        return self.locations[staff]

    def is_focused(self, staff: str) -> bool:
        action = self.active.get(staff)
        return action is not None and action.request.kind in ("prepare", "social", "right_bin")

    def social_peers(self, staff: str, now: int) -> tuple[str, ...]:
        if not self._social_available(staff, now):
            return ()
        return tuple(peer for peer in self.locations
                     if peer != staff and self.locations[peer] == self.locations[staff]
                     and self._social_available(peer, now))

    def _social_available(self, staff: str, now: int) -> bool:
        action = self.active.get(staff)
        return action is None or (action.request.kind == "leisure" and action.ends_at > now)

    def reserve_encounter(self, staff: str, peer: str, now: int, ends: int) -> tuple[int, int]:
        if peer not in self.social_peers(staff, now):
            raise ValueError("participants must be co-present and available")
        suspended = tuple(max(0, self.active[name].ends_at - now) if name in self.active else 0
                          for name in (staff, peer))
        for name in (staff, peer):
            self.active[name] = Action(Request("social"), ends)
        return suspended

    def release_encounter(self, staff: str, leisure_remaining: int, now: int) -> None:
        assert self.active[staff].request.kind == "social"
        if leisure_remaining:
            self.active[staff] = Action(Request("leisure"), now + leisure_remaining)
        else:
            del self.active[staff]

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
                             and job.ingredients <= ingredients
                             and not self.fitting_security.get(job.fitting, False))
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
        self, staff: str, request: Request, now: int, commitment: RepairCommitment | None,
        righting_progress: RightingProgress | None = None,
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
            if self.maintenance is not None and self.maintenance.crosses(location, request.destination):
                assert self.ecology is not None
                if self.ecology.wetness[self.maintenance.exposed_node] >= HEAVY_WETNESS:
                    duration = WET_TRAVEL_TIME
                action = RouteAction(request, now + duration, duration)
                self.active[staff] = action
                return action
        elif kind == "right_bin" and self.maintenance is not None:
            return self._start_righting(staff, request, now, righting_progress)
        elif kind == "inspect" and self.environment is not None:
            if request.destination is not None:
                raise ValueError("Inspection must be local")
            duration = INSPECTION_TIME
        elif kind == "prepare":
            if request.destination is not None:
                raise ValueError("malformed preparation request")
            job = self.jobs.get(request.target)
            if (job is None or self.job_states[job.target] != "pending"
                    or self.fitting_security.get(job.fitting, False)):
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

    def _start_righting(
        self, staff: str, request: Request, now: int, progress: RightingProgress | None,
    ) -> RightingAction:
        ecology = self.ecology
        assert ecology is not None
        if request.destination is not None or self.locations[staff] != ecology.config.refuse:
            raise ValueError("Righting requires the service yard")
        if "repair" not in self.capabilities.get(staff, ()):
            raise ValueError("Righting requires repair capability")
        if progress is not None and (not ecology.tipped or progress.revision != ecology.container_revision):
            raise ObsoleteRighting("Obsolete righting progress")
        if not ecology.tipped:
            raise ValueError("Container is upright")
        if self.righting is not None:
            raise ValueError("Container is reserved")
        self._righting_sequence += 1
        reservation = Reservation(staff, self._righting_sequence, ecology.container_revision)
        duration = progress.remaining if progress is not None else RIGHTING_TIME
        action = RightingAction(request, now + duration, reservation)
        self.righting = reservation
        self.active[staff] = action
        return action

    def suspend_righting(self, staff: str, now: int) -> RightingProgress | None:
        action = self.active.get(staff)
        if not isinstance(action, RightingAction) or self.righting != action.reservation or now >= action.ends_at:
            return None
        self.righting = None
        del self.active[staff]
        return RightingProgress(action.reservation.revision, action.ends_at - now)

    def complete_righting(self, staff: str, action: RightingAction, now: int) -> bool:
        ecology = self.ecology
        assert ecology is not None
        if (self.active.get(staff) is not action or self.righting != action.reservation
                or action.reservation.worker != staff or now != action.ends_at):
            return False
        self.righting = None
        del self.active[staff]
        if not ecology.tipped or ecology.container_revision != action.reservation.revision:
            return False
        ecology.tipped = False
        ecology.container_revision += 1
        return True

    def finish(self, staff: str) -> str:
        action = self.active[staff]
        if isinstance(action, RightingAction):
            raise ValueError("Righting completion requires the original action and timestamp")
        kind = action.request.kind
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
            outcome = {"cook": "cooked", "repair": "repaired", "cabin": "ready", "secure": "secured"}[job.category]
            if job.fitting is not None:
                self.fitting_security[job.fitting] = True
            if self.ecology is not None and job.category == "cook":
                self.ecology.add_scraps()
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

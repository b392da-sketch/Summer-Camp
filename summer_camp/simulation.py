"""Coordinate the clock, private decisions, world transitions, and history."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import partial
from random import Random
from types import MappingProxyType

from .clock import DAY, Clock
from .cognition import CAMP_DESTINATIONS, REASSESS, Mind, Staff, route
from .ecology import ANIMAL_INTERVAL, WEATHER_INTERVAL, Ecology, Incident, Transit
from .maintenance import Crossing, EnvironmentalMind, Maintenance, ObsoleteRighting
from .perception import (
    HOUR, MINUTE, Environment, Evidence, PerceptionMind, project, sound_distances,
)
from .social import (
    COOLDOWN, DURATION, PROMISE_WINDOW, Claim, Encounter, Exchange,
    Help, Relationship, SocialMind, SocialProfile, bound, observed_job,
)
from .testimony import REPORT_WINDOW, Payload, Testimony, TestimonyMind
from .world import PATHS, Action, Job, Observation, Request, RightingAction, RouteAction, World

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
    social: tuple[tuple[str, SocialProfile], ...] = ()
    environment: Environment | None = None
    witness_reports: bool = False
    ecology: Ecology | None = None
    maintenance: Maintenance | None = None

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
        if self.social and self.camp is None:
            raise ValueError("Social profiles require a camp layout")
        social_names = [name for name, _ in self.social]
        if len(social_names) != len(set(social_names)) or any(name not in names for name in social_names):
            raise ValueError("Social profiles must identify distinct staff")
        for name, profile in self.social:
            if any(peer not in names or peer == name for peer in profile.acquaintances):
                raise ValueError("Acquaintances must identify other staff")
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
        if self.witness_reports and (self.environment is None or not self.social):
            raise ValueError("Witness reports require perception and social profiles")
        if self.environment is not None:
            if self.camp is None:
                raise ValueError("Environmental perception requires a camp layout")
            self.environment.validate(paths, names)
        fittings = {item.key: item for item in self.environment.fittings} if self.environment else {}
        securing = [job for job in self.camp.jobs if job.fitting is not None] if self.camp else []
        if (len({job.fitting for job in securing}) != len(securing)
                or any(job.fitting not in fittings or fittings[job.fitting].location != job.location
                       for job in securing)):
            raise ValueError("Securing jobs need distinct fittings at their location")
        if self.ecology is not None:
            if self.environment is None or self.environment.nightly_target is not None:
                raise ValueError("Ecology requires perception without nightly disturbance scheduling")
            self.ecology.validate(paths)
            target = fittings.get(self.ecology.gust_target)
            if target is None or target.location not in self.ecology.exposed:
                raise ValueError("The gust fitting must be outdoors")

        if self.maintenance is not None:
            if self.ecology is None:
                raise ValueError("Maintenance requires an ecology")
            first, second = self.maintenance.wet_edge
            node = self.maintenance.exposed_node
            if (second not in paths.get(first, ()) or node not in (first, second)
                    or node not in self.ecology.exposed):
                raise ValueError("Wet route needs an exposed endpoint on a camp path")


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
            environment=scenario.environment,
            ecology=scenario.ecology,
            maintenance=scenario.maintenance,
        )
        self._social = {name: SocialMind.create(profile) for name, profile in scenario.social}
        self._encounters: dict[int, Encounter] = {}
        self._encounter_sequence = 0
        self._environmental = (
            {staff: EnvironmentalMind() for staff in self._minds} if scenario.maintenance is not None else {}
        )
        self._history: list[Event] = []
        self._wakes: dict[str, tuple[int, int]] = {}
        self._wake_sequence = 0
        self._perception: dict[str, PerceptionMind] = {}
        self._testimony = {staff: TestimonyMind() for staff in self._social} if scenario.witness_reports else {}
        self._disturbances: dict[int, tuple[int, str, str]] = {}
        self._disturbance_sequence = 0
        for staff in self._minds:
            self._schedule(staff, 0)
        if scenario.environment is not None:
            self._setup_environment(scenario.environment, seed, scenario.days)
        if scenario.ecology is not None:
            self._weather_rng = Random(seed ^ 0x4D35)
            self._clock.schedule(WEATHER_INTERVAL, self._weather_update)
            self._clock.schedule(ANIMAL_INTERVAL, self._animal_decision)

    def _setup_environment(self, environment: Environment, seed: int, days: int) -> None:
        curiosity = dict(environment.curiosity)
        self._perception = {staff: PerceptionMind(curiosity.get(staff, 0)) for staff in self._minds}
        if environment.nightly_target is None:
            return
        rng = Random(seed ^ 0x4D33)
        for day in range(days):
            when = day * DAY + rng.randrange(18 * HOUR, 23 * HOUR, MINUTE)
            self.queue_disturbance(when, environment.nightly_target, "gust")

    def queue_disturbance(self, when: int, target: str, cause: str) -> int:
        """Queue a simulated physical impulse, for fixture and controlled runs."""
        if target not in self._world.fitting_positions or not cause:
            raise ValueError("Disturbance needs a known fitting and a cause")
        if type(when) is not int or not self.now <= when <= self.horizon:
            raise ValueError("Disturbance must be within the simulated horizon")
        self._disturbance_sequence += 1
        key = self._disturbance_sequence
        self._disturbances[key] = (when, target, cause)
        self._clock.schedule(when, partial(self._resolve_disturbance, key))
        return key

    def cancel_disturbance(self, key: int) -> bool:
        return self._disturbances.pop(key, None) is not None

    def _resolve_disturbance(self, key: int) -> None:
        opportunity = self._disturbances.pop(key, None)
        if opportunity is None:
            return
        _, target, cause = opportunity
        self._disturb_fitting(target, cause)

    def _disturb_fitting(self, target: str, cause: str) -> None:
        physical = self._world.disturb(target, cause, self.now)
        if physical is None:
            return
        position = "open" if physical.opened else "closed"
        self._emit_incident(Incident(physical.cause, target, position, physical.stimulus))

    def _emit_incident(self, incident: Incident) -> None:
        stimulus = incident.stimulus
        self._record("environment", "occurred", "disturbance",
                     f"cause={incident.cause} target={incident.target} "
                     f"location={stimulus.location} position={incident.condition}")
        environment = self._world.environment
        assert environment is not None
        distances = sound_distances(stimulus.location, environment.acoustic)
        for staff in self._perception:
            location = self._world.perceptual_location(staff)
            if location is not None:
                self._remember(staff, project(stimulus, environment, location, distances,
                                              focused=self._world.is_focused(staff)))

    def _weather_update(self) -> None:
        ecology = self._world.ecology
        assert ecology is not None
        gust = ecology.update_weather(self._weather_rng, final=self.now == self.horizon)
        rain = "raining" if ecology.raining else "dry"
        self._record("environment", "updated", "weather",
                     f"wind={ecology.wind} rain={rain} wetness={ecology.wetness}")
        if gust:
            self._disturb_fitting(ecology.config.gust_target, "gust")
        when = self.now + WEATHER_INTERVAL
        if when <= self.horizon:
            self._clock.schedule(when, self._weather_update)

    def _animal_decision(self) -> None:
        ecology = self._world.ecology
        assert ecology is not None
        transit = ecology.decide(self.now, self.horizon)
        self._record("raccoon", "decided", "wildlife",
                     f"activity={ecology.raccoon.activity} hunger={ecology.raccoon.hunger}")
        if transit is not None:
            self._record("raccoon", "started", "wildlife travel",
                         f"from={transit.origin} to={transit.destination} arrival={transit.arrival}")
            self._clock.schedule(transit.arrival, partial(self._animal_arrival, transit))
        else:
            if ecology.raccoon.activity == "foraging":
                self._animal_forage()
            self._schedule_animal_decision()

    def _animal_arrival(self, transit: Transit) -> None:
        ecology = self._world.ecology
        assert ecology is not None
        if not ecology.arrive(transit, self.now):
            return
        self._record("raccoon", "completed", "wildlife travel", transit.destination)
        self._animal_forage()
        self._schedule_animal_decision()

    def _animal_forage(self) -> None:
        ecology = self._world.ecology
        assert ecology is not None
        scraps = ecology.scraps
        incident = ecology.forage(self.now)
        if ecology.scraps < scraps:
            self._record("raccoon", "completed", "forage", f"scraps={ecology.scraps}")
        if incident is not None:
            self._emit_incident(incident)

    def _schedule_animal_decision(self) -> None:
        when = self.now + ANIMAL_INTERVAL
        if when < self.horizon:
            self._clock.schedule(when, self._animal_decision)

    def _remember(self, staff: str, cues: tuple[Evidence, ...]) -> None:
        self._perception[staff].remember(cues)
        if staff in self._testimony:
            self._testimony[staff].compare(cues)
        for cue in cues:
            details = [cue.detail]
            if cue.area is not None:
                details.append(f"area={cue.area}")
            if cue.label is not None:
                details.append(f"object={cue.label}")
            self._record(staff, "perceived", cue.modality, " ".join(details))

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
        if self._social:
            state["social"] = {staff: asdict(mind) for staff, mind in self._social.items()}
            state["encounters"] = {key: asdict(value) for key, value in self._encounters.items()}
        if self._perception:
            state["perception"] = {staff: asdict(mind) for staff, mind in self._perception.items()}
            state["fitting_positions"] = dict(self._world.fitting_positions)
            state["disturbances"] = dict(self._disturbances)
        if self._testimony:
            state["testimony"] = {staff: asdict(mind) for staff, mind in self._testimony.items()}
        if self._world.ecology is not None:
            state["ecology"] = asdict(self._world.ecology)
        if self._perception:
            state["fitting_security"] = dict(self._world.fitting_security)
        if self._environmental:
            state["environmental_memory"] = {staff: asdict(mind) for staff, mind in self._environmental.items()}
            state["righting"] = asdict(self._world.righting) if self._world.righting is not None else None
        return state

    def _testimony_payload(self, staff: str, exchange: Exchange) -> Payload | None:
        state = self._testimony.get(staff)
        if (state is None or exchange.peer not in self._testimony or exchange.location is not None
                or exchange.target is not None or type(exchange.reference) is not int):
            return None
        ref = exchange.reference
        if exchange.kind == "testimony" and exchange.witness is None:
            for memory in self._perception[staff].memory:
                if memory.reference == ref and self.now + DURATION <= memory.evidence.at + REPORT_WINDOW:
                    return Payload(Testimony(staff, memory))
        if exchange.kind == "relay" and exchange.witness not in (None, exchange.peer, staff):
            received = state.accounts.get((exchange.witness, ref))
            if received is not None:
                delivery = received.delivery
                if not delivery.relayed and self.now + DURATION <= delivery.testimony.cue.at + REPORT_WINDOW:
                    return Payload(delivery.testimony, delivery.first_report_at, relayed=True)
        return None

    def propose_social(self, staff: str, exchange: Exchange) -> bool:
        """Propose an encounter through the same consent and availability rules as AI."""
        social = self._social.get(staff)
        peer = exchange.peer
        other = self._social.get(peer)
        ends = self.now + DURATION
        if (social is None or other is None or ends > self.horizon
                or peer not in self._world.social_peers(staff, self.now)):
            return False
        payload = None
        if exchange.kind in ("testimony", "relay"):
            payload = self._testimony_payload(staff, exchange)
            if payload is None or exchange.topic in social.topics:
                return False
        elif exchange.witness is not None or exchange.reference is not None:
            return False
        elif exchange.kind == "greet":
            if exchange.location is not None or exchange.target is not None:
                return False
        elif (exchange.kind not in ("ask", "report", "help") or exchange.location not in self._world.paths
              or not exchange.target or exchange.topic in social.topics):
            return False
        evidence = observed_job(self._minds[staff], exchange)
        if exchange.kind in ("report", "help") and (evidence is None or
                                                   (exchange.kind == "help" and evidence[0].done)):
            return False
        if self.now - social.approached.get(peer, -COOLDOWN) < COOLDOWN:
            return False
        for name in (staff, peer):
            self._minds[name].accrue(self.now)
        if not social.willing(self._minds[staff], peer, self.now):
            return False
        social.approached[peer] = self.now
        if not other.willing(self._minds[peer], staff, self.now):
            self._record(staff, "refused", "social", f"peer={peer}")
            return False
        other.heard[staff] = self.now
        suspended = self._world.reserve_encounter(staff, peer, self.now, ends)
        self._encounter_sequence += 1
        key = self._encounter_sequence
        self._encounters[key] = Encounter(staff, exchange, ends, suspended, payload)
        for name in (staff, peer):
            self._wakes.pop(name, None)
        self._record(staff, "started", "social", f"peer={peer} kind={exchange.kind}")
        self._clock.schedule(ends, partial(self._close_encounter, key))
        return True

    def disengage(self, staff: str) -> bool:
        """End an encounter without delivering its pending message."""
        for key, encounter in self._encounters.items():
            if staff in encounter.participants:
                self._close_encounter(key, cancelled=True)
                return True
        return False

    def _close_encounter(self, key: int, *, cancelled: bool = False) -> None:
        encounter = self._encounters.pop(key, None)
        if encounter is None:
            return
        staff, peer = encounter.participants
        if cancelled:
            detail = f"peer={peer} kind={encounter.exchange.kind}"
        else:
            detail = self._exchange(encounter)
            if encounter.exchange.kind != "greet":
                self._social[staff].topics.add(encounter.exchange.topic)
        self._record(staff, "cancelled" if cancelled else "completed", "social", detail)
        for name, remaining in zip(encounter.participants, encounter.leisure_remaining):
            self._world.release_encounter(name, remaining, self.now)
            if self.now < self.horizon:
                if remaining:
                    self._schedule(name, min(self.now + remaining, self.now + REASSESS, self.horizon))
                else:
                    self._schedule(name, self.now)

    def _exchange(self, encounter: Encounter) -> str:
        staff, peer = encounter.participants
        exchange = encounter.exchange
        detail = f"peer={peer} kind={exchange.kind}"
        for name, other in ((staff, peer), (peer, staff)):
            mind = self._minds[name]
            mind.accrue(self.now)
            social = self._social[name]
            social.last_exchange = self.now
            relation = social.relationships.setdefault(other, Relationship())
            relation.familiarity = min(5, relation.familiarity + 1)
            if exchange.kind == "greet" and social.profile.company > 0:
                relation.affinity = bound(relation.affinity + 1)
        if exchange.kind == "greet":
            return detail
        if encounter.payload is not None:
            return self._deliver_testimony(staff, peer, encounter.payload, detail)

        source, listener = (peer, staff) if exchange.kind == "ask" else (staff, peer)
        evidence = observed_job(self._minds[source], exchange)
        if evidence is None:
            return f"{detail} reply=unknown"
        job, at = evidence
        claim = Claim(source, exchange.location, exchange.target, "complete" if job.done else "pending",
                      at, self.now)
        recipient = self._social[listener]
        recipient.claims.append(claim)
        detail += (f" source={source} location={claim.location} target={claim.target}"
                   f" value={claim.value} observed={claim.observed_at}")
        if exchange.kind == "help":
            mind = self._minds[listener]
            if job.capability not in mind.profile.capabilities or recipient.profile.helpfulness < 0:
                response = "declined"
            elif (mind.camp_break(self.now, self._world.locations[listener])
                  or any(promise.state == "accepted" for promise in recipient.help)):
                response = "deferred"
            else:
                response = "accepted"
            recipient.help.append(Help(claim, self.now + PROMISE_WINDOW, response))
            self._social[staff].responses.append((listener, claim.target, response, self.now))
            if response == "declined":
                relation = self._social[staff].relationships[listener]
                relation.affinity = bound(relation.affinity - 1)
            detail += f" response={response}"
        return detail

    def _deliver_testimony(self, staff: str, peer: str, payload: Payload, detail: str) -> str:
        report = payload.testimony
        cue = report.cue
        if not payload.relayed:
            sender = self._testimony[staff]
            sender.first_reports = {
                ref: timing for ref, timing in sender.first_reports.items() if timing[1] >= self.now
            }
            first, _ = sender.first_reports.setdefault(report.observation.reference,
                                                        (self.now, cue.at + REPORT_WINDOW))
            payload = Payload(report, first)
        relation = self._social[peer].relationships[staff]
        received = self._testimony[peer].receive(payload, staff, self.now,
                                                 self._perception[peer].curiosity, relation.trust)
        if received and peer in self._environmental:
            account = self._testimony[peer].accounts[report.origin]
            ecology = self._world.ecology
            assert ecology is not None
            if (account.assessment == "credible" and cue.modality in ("notice", "inspection")
                    and cue.detail == "tipped container" and cue.label == "refuse container"
                    and cue.area == ecology.config.refuse):
                self._environmental[peer].consider_report(report.witness, report.observation.reference, cue, self.now)
        status = "received" if received else "duplicate"
        return (f"{detail} witness={report.witness} reference={report.observation.reference}"
                f" observed={cue.at} cue={cue.detail} area={cue.area or 'unknown'} delivery={status}")

    def cancel_preparation(self, staff: str) -> bool:
        """Cancel an active M1 job, releasing reservations and discarding its progress."""
        action = self._world.active.get(staff)
        if action is None or action.request.kind != "prepare" or self.now == self.horizon:
            return False
        commitment = self._world.interrupt_work(staff, self.now)
        self._record(staff, "cancelled", "prepare", f"target={commitment.target}")
        self._schedule(staff, self.now)
        return True

    def cancel_maintenance(self, staff: str) -> bool:
        if self.now == self.horizon or self._world.suspend_righting(staff, self.now) is None:
            return False
        self._record(staff, "cancelled", "right_bin")
        self._schedule(staff, self.now)
        return True

    def _check_container(self, staff: str, cue: Evidence) -> bool:
        memory = self._environmental[staff]
        changed = memory.notice(cue)
        if cue.detail == "upright container" and memory.visit is not None:
            self._record(staff, "abandoned", "maintenance visit", "container observed upright")
            memory.visit = None
        if not changed and staff in self._testimony:
            self._testimony[staff].compare((cue,))
        return changed

    def _inspection_cues(self, staff: str) -> tuple[tuple[Evidence, ...], bool]:
        location = self._world.locations[staff]
        cues = self._world.inspect(location, self.now)
        if staff not in self._environmental:
            return cues, bool(cues)
        ecology = self._world.ecology
        assert ecology is not None
        findings = []
        for cue in cues:
            if cue.label != "refuse container" or self._check_container(staff, cue):
                findings.append(cue)
        if location == ecology.config.refuse:
            self._environmental[staff].visit = None
        return tuple(findings), bool(cues)

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
        environmental = self._environmental.get(staff)
        progress = environmental.progress if environmental is not None and request.kind == "right_bin" else None
        try:
            action = self._world.start(staff, request, self.now, commitment, progress)
        except ValueError as error:
            if isinstance(error, ObsoleteRighting) and environmental is not None:
                environmental.progress = None
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
            if isinstance(action, RouteAction):
                detail += f" duration={action.duration}s"
        elif isinstance(action, RightingAction):
            detail = f"revision={action.reservation.revision} ticket={action.reservation.ticket}"
            if progress is not None:
                phase = "resumed"
            assert environmental is not None
            environmental.progress = None
            environmental.visit = None
        if mind.profile is not None:
            mind.accrue(self.now)
        if kind == "sleep":
            detail = f"duration={action.ends_at - self.now}s"
        self._record(staff, phase, kind, detail)
        mind.travel_goal = goal if kind == "move" else None
        if phase == "resumed" and kind != "right_bin":
            if kind == "prepare":
                del mind.preparations[commitment.target]
            else:
                mind.repair_commitment = None
        when = self._next_check(kind, action.ends_at)
        if staff in self._social and kind == "leisure":
            when = min(when, self.now + REASSESS, self.horizon)
        self._schedule(staff, when)
        return True

    def _next_check(self, kind: str, ends_at: int) -> int:
        if kind in ("prepare", "sleep", "right_bin"):
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
            if isinstance(action, RouteAction):
                origin = self._world.locations[staff]
                destination = action.request.destination
                assert destination is not None
                self._environmental[staff].crossing = Crossing(origin, destination, action.duration, self.now)
            if isinstance(action, RightingAction):
                changed = self._world.complete_righting(staff, action, self.now)
                phase = "completed" if changed else "failed"
                detail = "tipped -> upright" if changed else "Obsolete righting action"
            else:
                detail = self._world.finish(staff)
                phase = "completed"
            if kind != "move":
                mind.satisfy(kind)
            if kind == "inspect":
                cues, observed = self._inspection_cues(staff)
                self._remember(staff, cues)
                detail = "local condition observed" if observed else "inconclusive"
            self._record(staff, phase, kind, detail)
            if kind == "prepare" and staff in self._social:
                for promise in self._social[staff].help:
                    if promise.claim.target == action.request.target and promise.state == "accepted":
                        if self.now < promise.expires:
                            promise.state = "fulfilled"
                            self._record(staff, "fulfilled", "help", f"target={promise.claim.target}")
                        else:
                            promise.state = "expired"
            action = None

        if staff in self._environmental:
            cue = self._world.notice_container(staff, self.now)
            if cue is not None and self._check_container(staff, cue):
                self._remember(staff, (cue,))
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
        social = self._social.get(staff)
        if social is not None:
            social.assess(location, local_jobs.jobs if local_jobs is not None else (), self.now)
        if self.now == self.horizon:
            return
        if action is not None:
            kind = action.request.kind
            reason = mind.camp_break(self.now, location) if kind in ("prepare", "right_bin") else None
            if reason is None:
                if social is not None and kind == "leisure":
                    if self._consider_social(staff, mind, social):
                        return
                    self._schedule(staff, min(action.ends_at, self.now + REASSESS, self.horizon))
                else:
                    self._schedule(staff, self._next_check(kind, action.ends_at))
                return
            if kind == "right_bin":
                progress = self._world.suspend_righting(staff, self.now)
                assert progress is not None
                self._environmental[staff].progress = progress
                self._record(staff, "interrupted", kind,
                             f"revision={progress.revision}, {reason}, {progress.remaining}s remaining")
            else:
                commitment = self._world.interrupt_work(staff, self.now)
                mind.preparations[commitment.target] = commitment
                self._record(staff, "interrupted", kind,
                             f"target={commitment.target}, {reason}, {commitment.remaining}s remaining")
            # The worker is still present and can see the slot they just released.
            mind.memory.update(self._world.observe(staff, self.now))

        help_intent = social.intent(mind, location, self.now) if social is not None else None
        seek_company = social is not None and social.seeks_company(self.now)
        perception = self._perception.get(staff)
        testimony = self._testimony.get(staff)
        investigation = None
        inspection = None
        if perception is not None:
            if testimony is None:
                inspection = perception.candidate(self.now)
            else:
                investigation = testimony.candidate(staff, perception, self.now)
                if investigation is not None:
                    inspection = (investigation.area, investigation.score)
        upkeep = self._maintenance_choice(staff, mind, location)
        decision = mind.choose_camp(location, self.now, self._world.paths, help_intent, seek_company, inspection, upkeep)
        if testimony is not None and testimony.travelling is not None:
            if decision is None or decision[0] != f"investigate:{testimony.travelling.area}":
                testimony.travelling = None
        elif testimony is None and perception is not None and mind.travel_goal and mind.travel_goal.startswith("investigate:"):
            if decision is None or decision[0] != mind.travel_goal:
                perception.clear_pending()
        if social is not None and (decision is None or decision[0] == "leisure"):
            if self._consider_social(staff, mind, social):
                return
        if decision is not None:
            goal, request = decision
            if self._start(staff, request, goal):
                if testimony is not None and investigation is not None and goal == f"investigate:{investigation.area}":
                    if testimony.travelling is None:
                        source = "firsthand" if investigation.firsthand else "testimony"
                        self._record(staff, "selected", "investigation",
                                     f"source={source} witness={investigation.origin[0]} "
                                     f"reference={investigation.origin[1]} area={investigation.area}")
                    assert perception is not None
                    testimony.depart(investigation, perception, moving=request.kind == "move")
                elif perception is not None and request.kind == "inspect":
                    perception.clear_pending()
                return
        mind.travel_goal = None
        self._schedule(staff, min(self.now + REASSESS, self.horizon))

    def _maintenance_choice(self, staff: str, mind: Mind, location: str) -> tuple[str, int, Request] | None:
        memory = self._environmental.get(staff)
        if memory is None or mind.profile is None:
            return None
        ecology = self._world.ecology
        assert ecology is not None
        yard = ecology.config.refuse
        if memory.visit is not None and self.now >= memory.visit.expires:
            memory.visit = None
        if "repair" not in mind.profile.capabilities:
            return None
        score = 37 + mind.preferences["work"]
        if yard in mind.profile.responsibilities:
            score += 12
        if memory.progress is not None:
            score += 8
        if score <= 15:
            return None
        if location == yard and memory.checked is not None and memory.checked.checked_at == self.now:
            if memory.checked.condition == "tipped container":
                return yard, score, Request("right_bin")
            return None
        if memory.visit is not None:
            return yard, score, Request("inspect")
        return None

    def _sensory_proposal(self, staff: str, peer: str) -> Exchange | None:
        social = self._social[staff]
        relation = social.relationships.get(peer, Relationship())
        inclination = social.profile.company + relation.affinity + relation.trust
        if inclination < 1:
            return None
        options: list[tuple[int, Exchange]] = []
        state = self._testimony[staff]
        sources = [
            (Exchange(peer, "relay", witness=witness, reference=ref), account.delivery.testimony.cue)
            for (witness, ref), account in state.accounts.items()
            if not account.delivery.relayed and witness != peer and account.assessment == "credible"
        ]
        sources.extend((Exchange(peer, "testimony", reference=memory.reference), memory.evidence)
                       for memory in self._perception[staff].memory)
        for exchange, cue in sources:
            age = self.now - cue.at
            if exchange.topic in social.topics or age + DURATION > REPORT_WINDOW:
                continue
            significance = 3 if cue.label is not None or cue.detail == "clatter" else 1
            score = significance + inclination - age // (4 * HOUR)
            if score >= 2:
                options.append((score, exchange))
        return max(options, key=lambda item: item[0])[1] if options else None

    def _consider_social(self, staff: str, mind: Mind, social: SocialMind) -> bool:
        peers = tuple(peer for peer in self._world.social_peers(staff, self.now) if peer in self._social)
        sensory = partial(self._sensory_proposal, staff) if staff in self._testimony else None
        exchange = social.proposal(mind, peers, self.now, sensory)
        return exchange is not None and self.propose_social(staff, exchange)

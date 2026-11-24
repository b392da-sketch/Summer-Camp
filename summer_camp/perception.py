"""Physical event descriptions, sensory projection, and private cue memory."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from heapq import heappop, heappush

from .clock import DAY

MINUTE = 60
HOUR = 60 * MINUTE
INSPECTION_TIME = 5 * MINUTE
CUE_LIFETIME = 75 * MINUTE
MEMORY_SIZE = 8


@dataclass(frozen=True)
class Link:
    first: str
    second: str
    loss: int

    def __post_init__(self):
        if self.first == self.second or type(self.loss) is not int or self.loss < 1:
            raise ValueError("Sensory links require distinct endpoints and positive loss")


@dataclass(frozen=True)
class Fitting:
    key: str
    label: str
    location: str
    loose: bool = True
    strength: int = 8

    def __post_init__(self):
        if not self.key or not self.label or type(self.strength) is not int or self.strength < 1:
            raise ValueError("A fitting needs an identity, visible label and positive sound strength")


@dataclass(frozen=True)
class Environment:
    fittings: tuple[Fitting, ...]
    acoustic: tuple[Link, ...] = ()
    sightlines: tuple[Link, ...] = ()
    lamps: tuple[tuple[str, int], ...] = ()
    curiosity: tuple[tuple[str, int], ...] = ()
    nightly_target: str | None = None

    def validate(self, paths: Mapping[str, tuple[str, ...]], staff: list[str]) -> None:
        keys = {fitting.key for fitting in self.fittings}
        if len(keys) != len(self.fittings) or any(item.location not in paths for item in self.fittings):
            raise ValueError("Fittings need unique identities and known locations")
        if self.nightly_target is not None and self.nightly_target not in keys:
            raise ValueError("Unknown nightly fitting")
        for links in (self.acoustic, self.sightlines):
            pairs = {frozenset((edge.first, edge.second)) for edge in links}
            if len(pairs) != len(links) or any(not pair <= paths.keys() for pair in pairs):
                raise ValueError("Sensory links need distinct pairs of known locations")
        if (len(dict(self.lamps)) != len(self.lamps)
                or any(node not in paths or type(light) is not int or light < 0 for node, light in self.lamps)):
            raise ValueError("Lamps need unique known locations and nonnegative levels")
        if (len(dict(self.curiosity)) != len(self.curiosity)
                or any(name not in staff or type(value) is not int for name, value in self.curiosity)):
            raise ValueError("Curiosity needs unique known staff and integer preferences")

    def light(self, node: str, now: int) -> int:
        daylight = 3 if 6 * HOUR <= now % DAY < 18 * HOUR else 0
        return daylight + dict(self.lamps).get(node, 0)


@dataclass(frozen=True)
class PhysicalEvent:
    at: int
    fitting: Fitting
    cause: str
    opened: bool


@dataclass(frozen=True)
class Evidence:
    at: int
    modality: str
    detail: str
    area: str | None = None
    label: str | None = None


def sound_distances(source: str, links: tuple[Link, ...]) -> dict[str, int]:
    """Least attenuation from the source across the separate acoustic graph."""
    neighbors: dict[str, list[tuple[str, int]]] = {}
    for edge in links:
        neighbors.setdefault(edge.first, []).append((edge.second, edge.loss))
        neighbors.setdefault(edge.second, []).append((edge.first, edge.loss))
    distances = {source: 0}
    pending = [(0, source)]
    while pending:
        distance, node = heappop(pending)
        if distance != distances[node]:
            continue
        for peer, loss in neighbors.get(node, ()):
            candidate = distance + loss
            if peer not in distances or candidate < distances[peer]:
                distances[peer] = candidate
                heappush(pending, (candidate, peer))
    return distances


def project(
    event: PhysicalEvent, environment: Environment, listener: str,
    distances: dict[str, int], *, focused: bool = False,
) -> tuple[Evidence, ...]:
    source = event.fitting.location
    attention_loss = 1 if focused else 0
    cues = []
    sight_loss = 0 if listener == source else next(
        (edge.loss for edge in environment.sightlines
         if {edge.first, edge.second} == {listener, source}), None,
    )
    if sight_loss is not None:
        detail = environment.light(source, event.at) - sight_loss - attention_loss
        if detail >= 1:
            label = event.fitting.label if detail >= 3 else None
            cues.append(Evidence(event.at, "vision", "moving" if label else "motion", source, label))

    if listener in distances:
        strength = event.fitting.strength - distances[listener] - attention_loss
        if strength >= 2:
            direction = None
            if strength >= 4:
                if listener == source:
                    direction = listener
                else:
                    approaches = []
                    for edge in environment.acoustic:
                        if listener not in (edge.first, edge.second):
                            continue
                        peer = edge.second if listener == edge.first else edge.first
                        if peer in distances and edge.loss + distances[peer] == distances[listener]:
                            approaches.append(peer)
                    if len(approaches) == 1:
                        direction = approaches[0]
            detail = "clatter" if strength >= 4 else "indistinct noise"
            cues.append(Evidence(event.at, "sound", detail, direction))
    return tuple(cues)


def inspect(environment: Environment, location: str, now: int) -> tuple[Evidence, ...]:
    """Inspect current local conditions, with no access to past physical events."""
    if environment.light(location, now) + 1 < 3:
        return ()
    return tuple(
        Evidence(now, "inspection", "loose latch" if item.loose else "secure latch", location, item.label)
        for item in environment.fittings if item.location == location
    )


@dataclass(frozen=True)
class Interpretation:
    reference: int
    evidence: Evidence
    possibility: str


@dataclass
class PerceptionMind:
    curiosity: int
    memory: list[Interpretation] = field(default_factory=list)
    pending: Evidence | None = None
    pending_reference: int | None = None
    sequence: int = 0

    def clear_pending(self) -> None:
        self.pending = None
        self.pending_reference = None

    def remember(self, cues: tuple[Evidence, ...]) -> None:
        for cue in cues:
            if cue.modality == "inspection":
                guess = "current local condition"
            elif cue.modality == "vision":
                guess = "something moved"
            else:
                guess = "something may have shifted" if cue.detail == "clatter" else "unexplained noise"
            self.sequence += 1
            self.memory.append(Interpretation(self.sequence, cue, guess))
        del self.memory[:-MEMORY_SIZE]
        if self.pending is not None:
            if not cues or cues[0].at - self.pending.at < CUE_LIFETIME:
                return
            self.clear_pending()
        for index, cue in enumerate(cues):
            if cue.area is not None and cue.modality != "inspection":
                self.pending = cue
                self.pending_reference = self.sequence - len(cues) + index + 1
                break

    def candidate(self, now: int) -> tuple[str, int] | None:
        if self.pending is not None and now - self.pending.at >= CUE_LIFETIME:
            self.clear_pending()
        if self.pending is not None and self.pending.area is not None and self.curiosity > 0:
            return self.pending.area, 34 + self.curiosity
        return None

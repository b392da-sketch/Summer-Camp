"""One reusable container task and private environmental knowledge."""

from dataclasses import dataclass

from .perception import CUE_LIFETIME, MINUTE, Evidence

RIGHTING_TIME = 30 * MINUTE
HEAVY_WETNESS = 3
WET_TRAVEL_TIME = 15 * MINUTE


@dataclass(frozen=True)
class Maintenance:
    wet_edge: tuple[str, str]
    exposed_node: str

    def crosses(self, origin: str, destination: str) -> bool:
        return (origin, destination) in (self.wet_edge, self.wet_edge[::-1])


@dataclass(frozen=True)
class Reservation:
    worker: str
    ticket: int
    revision: int


@dataclass(frozen=True)
class RightingProgress:
    revision: int
    remaining: int


class ObsoleteRighting(ValueError):
    """A suspended task no longer refers to the current physical problem."""


@dataclass(frozen=True)
class LocalCheck:
    condition: str
    checked_at: int


@dataclass(frozen=True)
class Visit:
    witness: str
    reference: int
    expires: int


@dataclass(frozen=True)
class Crossing:
    origin: str
    destination: str
    elapsed: int
    arrived_at: int


@dataclass
class EnvironmentalMind:
    checked: LocalCheck | None = None
    visit: Visit | None = None
    progress: RightingProgress | None = None
    crossing: Crossing | None = None

    def notice(self, cue: Evidence) -> bool:
        previous = self.checked
        self.checked = LocalCheck(cue.detail, cue.at)
        return previous.condition != cue.detail if previous is not None else cue.detail == "tipped container"

    def consider_report(self, witness: str, reference: int, cue: Evidence, now: int) -> None:
        expires = cue.at + CUE_LIFETIME
        if now < expires and (self.visit is None or now >= self.visit.expires):
            self.visit = Visit(witness, reference, expires)

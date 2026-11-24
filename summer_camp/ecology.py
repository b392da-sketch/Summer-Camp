"""Small, observer-independent weather and wildlife state machines."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from random import Random

from .perception import HOUR, MINUTE, Stimulus

WEATHER_INTERVAL = 3 * HOUR
ANIMAL_INTERVAL = 30 * MINUTE
SCRAP_CAPACITY = 6
WETNESS_LIMIT = 4
WIND = ("calm", "breezy", "gusty")
WIND_WEIGHTS = {"calm": (7, 3, 0), "breezy": (2, 5, 3), "gusty": (0, 4, 6)}


@dataclass(frozen=True)
class Trail:
    first: str
    second: str
    duration: int = 10 * MINUTE

    def __post_init__(self):
        if self.first == self.second or type(self.duration) is not int or self.duration <= 0:
            raise ValueError("Trails need distinct endpoints and a positive integer duration")


@dataclass(frozen=True)
class Ecology:
    exposed: tuple[str, ...]
    gust_target: str
    den: str
    refuse: str
    trails: tuple[Trail, ...]
    refuse_accessible: bool = True
    initial_wind: str = "breezy"
    initial_raining: bool = False

    def validate(self, paths: Mapping[str, tuple[str, ...]]) -> None:
        if self.initial_wind not in WIND:
            raise ValueError("Unknown initial wind state")
        if not set(self.exposed) <= paths.keys() or len(set(self.exposed)) != len(self.exposed):
            raise ValueError("Exposed areas need distinct known locations")
        if (self.den == self.refuse or self.den not in paths or self.refuse not in paths["kitchen"]
                or self.refuse not in self.exposed):
            raise ValueError("Refuse needs a service area next to the kitchen, separate from the den")
        pairs = {frozenset((trail.first, trail.second)) for trail in self.trails}
        if len(pairs) != len(self.trails) or any(not pair <= paths.keys() for pair in pairs):
            raise ValueError("Wildlife trails need distinct pairs of known locations")
        if next_step(self.den, self.refuse, self.trails) is None:
            raise ValueError("Wildlife trails must connect the den to refuse")


@dataclass(frozen=True)
class Transit:
    origin: str
    destination: str
    arrival: int


@dataclass
class Animal:
    location: str | None
    transit: Transit | None = None
    hunger: int = 2
    activity: str = "resting"


@dataclass(frozen=True)
class Incident:
    cause: str
    target: str
    condition: str
    stimulus: Stimulus


@dataclass
class EcologyState:
    config: Ecology
    wind: str = field(init=False)
    raining: bool = field(init=False)
    wetness: dict[str, int] = field(init=False)
    raccoon: Animal = field(init=False)
    scraps: int = 0
    tipped: bool = False
    container_revision: int = 0

    def __post_init__(self):
        self.wind = self.config.initial_wind
        self.raining = self.config.initial_raining
        self.wetness = dict.fromkeys(self.config.exposed, 0)
        self.raccoon = Animal(self.config.den)

    def update_weather(self, rng: Random, *, final: bool = False) -> bool:
        for node, wetness in self.wetness.items():
            change = 2 if self.raining else -1
            self.wetness[node] = max(0, min(WETNESS_LIMIT, wetness + change))
        if final:
            return False
        previous = self.wind
        self.wind = rng.choices(WIND, weights=WIND_WEIGHTS[previous], k=1)[0]
        self.raining = rng.randrange(10) < (7 if self.raining else 2)
        return previous != "gusty" and self.wind == "gusty"

    def add_scraps(self) -> None:
        self.scraps = min(SCRAP_CAPACITY, self.scraps + 2)

    def decide(self, now: int, horizon: int) -> Transit | None:
        animal = self.raccoon
        if animal.location is None:
            return None
        animal.hunger = min(8, animal.hunger + 1)
        # Rain favours shelter unless hunger is pressing.
        threshold = 6 if self.raining else 3
        wants_food = self.config.refuse_accessible and self.scraps > 0 and animal.hunger >= threshold
        destination = self.config.refuse if wants_food else self.config.den
        animal.activity = "foraging" if wants_food else "resting"
        if destination == animal.location:
            return None
        step = next_step(animal.location, destination, self.config.trails)
        if step is None:
            return None
        peer, duration = step
        if now + duration > horizon:
            return None
        transit = Transit(animal.location, peer, now + duration)
        animal.transit = transit
        animal.location = None
        animal.activity = "travelling"
        return transit

    def arrive(self, transit: Transit, now: int) -> bool:
        animal = self.raccoon
        if animal.transit is not transit or now != transit.arrival:
            return False
        animal.transit = None
        animal.location = transit.destination
        animal.activity = "resting" if animal.location == self.config.den else "foraging"
        return True

    def forage(self, now: int) -> Incident | None:
        animal = self.raccoon
        if animal.location != self.config.refuse or not self.config.refuse_accessible or self.scraps <= 0:
            return None
        self.scraps -= 1
        animal.hunger = max(0, animal.hunger - 4)
        if self.tipped:
            return None
        self.tipped = True
        self.container_revision += 1
        return Incident("raccoon contact", "refuse container", "tipped",
                        Stimulus(now, self.config.refuse, "raccoon", 8))


def next_step(origin: str, target: str, trails: tuple[Trail, ...]) -> tuple[str, int] | None:
    pending: list[tuple[str, tuple[str, int] | None]] = [(origin, None)]
    visited = {origin}
    for node, first in pending:
        if node == target:
            return first
        for trail in trails:
            if node not in (trail.first, trail.second):
                continue
            peer = trail.second if node == trail.first else trail.first
            if peer not in visited:
                visited.add(peer)
                pending.append((peer, first or (peer, trail.duration)))
    return None

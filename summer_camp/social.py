"""Private social beliefs and short, structured exchanges."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .testimony import Payload
from .world import MINUTE, JobOffer, Request

if TYPE_CHECKING:
    from .cognition import Mind

HOUR = 60 * MINUTE
DURATION = 5 * MINUTE
COOLDOWN = 4 * HOUR
SOCIAL_REST = 45 * MINUTE
PROMISE_WINDOW = COOLDOWN


@dataclass(frozen=True)
class SocialProfile:
    company: int = 0
    helpfulness: int = 0
    acquaintances: tuple[str, ...] = ()


@dataclass(frozen=True)
class Exchange:
    peer: str
    kind: str = "greet"
    location: str | None = None
    target: str | None = None
    witness: str | None = None
    reference: int | None = None

    @property
    def topic(self) -> tuple:
        if self.kind in ("testimony", "relay"):
            return (self.peer, self.kind, self.witness, self.reference)
        return (self.peer, self.kind, self.location, self.target)


@dataclass(frozen=True)
class Claim:
    speaker: str
    location: str
    target: str
    value: str
    observed_at: int
    delivered_at: int


@dataclass
class Help:
    claim: Claim
    expires: int
    state: str


@dataclass
class Relationship:
    familiarity: int = 0
    affinity: int = 0
    trust: int = 0


@dataclass(frozen=True)
class Encounter:
    speaker: str
    exchange: Exchange
    ends: int
    leisure_remaining: tuple[int, int]
    payload: Payload | None = None

    @property
    def participants(self) -> tuple[str, str]:
        return self.speaker, self.exchange.peer


@dataclass
class SocialMind:
    profile: SocialProfile
    relationships: dict[str, Relationship] = field(default_factory=dict)
    claims: list[Claim] = field(default_factory=list)
    assessed: dict[int, str] = field(default_factory=dict)
    help: list[Help] = field(default_factory=list)
    approached: dict[str, int] = field(default_factory=dict)
    topics: set[tuple] = field(default_factory=set)
    responses: list[tuple[str, str, str, int]] = field(default_factory=list)
    heard: dict[str, int] = field(default_factory=dict)
    last_exchange: int = -SOCIAL_REST

    @classmethod
    def create(cls, profile: SocialProfile) -> "SocialMind":
        return cls(profile, {peer: Relationship(familiarity=1) for peer in profile.acquaintances})

    def willing(self, mind: "Mind", peer: str, now: int) -> bool:
        affinity = self.relationships.get(peer, Relationship()).affinity
        return (
            self.profile.company + affinity >= -2
            and mind.needs["rest"] < 80 * HOUR
            and mind.needs["meal"] < 75 * HOUR
            and now - self.heard.get(peer, -COOLDOWN) >= COOLDOWN
        )

    def seeks_company(self, now: int) -> bool:
        return self.profile.company > 0 and now - self.last_exchange >= SOCIAL_REST

    def proposal(
        self, mind: "Mind", peers: tuple[str, ...], now: int,
        sensory_proposal: Callable[[str], Exchange | None] | None = None,
    ) -> Exchange | None:
        if self.profile.company < 0 or now - self.last_exchange < SOCIAL_REST:
            return None
        for peer in peers:
            if not self.willing(mind, peer, now) or now - self.approached.get(peer, -COOLDOWN) < COOLDOWN:
                continue
            for key, observation in mind.memory.items():
                if not key.startswith("prepare:"):
                    continue
                location = key.removeprefix("prepare:")
                for job in observation.jobs:
                    request = Exchange(peer, "help", location, job.target)
                    if (not job.done and job.capability not in mind.profile.capabilities
                            and request.topic not in self.topics):
                        return request
            if sensory_proposal is not None:
                proposal = sensory_proposal(peer)
                if proposal is not None:
                    return proposal
            return Exchange(peer)
        return None

    def assess(self, location: str, jobs: tuple[JobOffer, ...], now: int) -> None:
        by_target = {job.target: job for job in jobs}
        for index, claim in enumerate(self.claims):
            job = by_target.get(claim.target)
            if claim.location != location or job is None or index in self.assessed:
                continue
            # Pending reports can become stale through normal work. Give credit
            # for confirmation or discount disagreement as current guidance.
            matches = job.done == (claim.value == "complete")
            relation = self.relationships.setdefault(claim.speaker, Relationship())
            relation.trust = bound(relation.trust + (1 if matches else 0))
            self.assessed[index] = "confirmed" if matches else "contradicted"
        for promise in self.help:
            if promise.state != "accepted":
                continue
            claim = promise.claim
            job = by_target.get(claim.target)
            if now >= promise.expires:
                promise.state = "expired"
            elif claim.location == location and job is not None and job.done:
                promise.state = "obsolete"

    def intent(self, mind: "Mind", location: str, now: int) -> tuple[str, Request] | None:
        for promise in self.help:
            if promise.state != "accepted" or now >= promise.expires:
                continue
            claim = promise.claim
            last_seen = mind.memory.get(f"prepare:{claim.location}")
            if last_seen is not None:
                job = next((job for job in last_seen.jobs if job.target == claim.target), None)
                if job is None or job.done:
                    continue
                if not job.available and (claim.location == location or now - last_seen.at < HOUR):
                    continue
            if claim.location != location or last_seen is not None:
                return claim.location, Request("prepare", target=claim.target)
        return None


def observed_job(mind: "Mind", exchange: Exchange) -> tuple[JobOffer, int] | None:
    observation = mind.memory.get(f"prepare:{exchange.location}")
    if observation is not None:
        for job in observation.jobs:
            if job.target == exchange.target:
                return job, observation.at
    return None


def bound(value: int) -> int:
    return max(-5, min(5, value))

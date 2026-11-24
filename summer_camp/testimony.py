"""Witness-local provenance and private assessments of received evidence."""

from dataclasses import dataclass, field

from .perception import CUE_LIFETIME, HOUR, Evidence, Interpretation, PerceptionMind

REPORT_WINDOW = 18 * HOUR
ACCOUNT_LIMIT = 12


@dataclass(frozen=True)
class Testimony:
    witness: str
    observation: Interpretation

    @property
    def origin(self) -> tuple[str, int]:
        return self.witness, self.observation.reference

    @property
    def cue(self) -> Evidence:
        return self.observation.evidence


@dataclass(frozen=True)
class Payload:
    testimony: Testimony
    first_report_at: int | None = None
    relayed: bool = False


@dataclass(frozen=True)
class Delivery:
    testimony: Testimony
    speaker: str
    first_report_at: int
    delivered_at: int
    relayed: bool


@dataclass(frozen=True)
class Investigation:
    origin: tuple[str, int]
    area: str
    expires: int
    score: int
    firsthand: bool


@dataclass
class Received:
    delivery: Delivery
    assessment: str
    compared: str | None = None


@dataclass
class TestimonyMind:
    accounts: dict[tuple[str, int], Received] = field(default_factory=dict)
    seen_until: dict[tuple[str, int], int] = field(default_factory=dict)
    first_reports: dict[int, tuple[int, int]] = field(default_factory=dict)
    pending: Investigation | None = None
    travelling: Investigation | None = None

    def receive(self, payload: Payload, speaker: str, now: int, curiosity: int, trust: int) -> bool:
        testimony = payload.testimony
        self.seen_until = {key: expires for key, expires in self.seen_until.items() if expires >= now}
        if testimony.origin in self.seen_until:
            return False
        first = payload.first_report_at if payload.first_report_at is not None else now
        delivery = Delivery(testimony, speaker, first, now, payload.relayed)
        self.seen_until[testimony.origin] = testimony.cue.at + REPORT_WINDOW
        if len(self.accounts) == ACCOUNT_LIMIT:
            del self.accounts[next(iter(self.accounts))]
        cue = testimony.cue
        assessment = "credible" if trust >= -1 else "doubtful"
        if curiosity <= 0:
            assessment = "disregarded"
        self.accounts[testimony.origin] = Received(delivery, assessment)
        expires = cue.at + CUE_LIFETIME
        if self.pending is not None and now >= self.pending.expires:
            self.pending = None
        if (assessment == "credible" and cue.area is not None and cue.modality != "inspection"
                and now < expires and self.pending is None and self.travelling is None):
            score = 31 + curiosity + 2 * trust - (4 if payload.relayed else 0)
            self.pending = Investigation(testimony.origin, cue.area, expires, score, False)
        return True

    def candidate(self, staff: str, perception: PerceptionMind, now: int) -> Investigation | None:
        direct = perception.candidate(now)
        if self.pending is not None and now >= self.pending.expires:
            self.pending = None
        if self.travelling is not None:
            if now < self.travelling.expires:
                return self.travelling
            self.travelling = None
        if direct is not None and (self.pending is None or direct[1] >= self.pending.score):
            assert perception.pending is not None and perception.pending_reference is not None
            return Investigation((staff, perception.pending_reference), direct[0],
                                 perception.pending.at + CUE_LIFETIME, direct[1], True)
        return self.pending

    def depart(self, investigation: Investigation, perception: PerceptionMind, *, moving: bool) -> None:
        if investigation.firsthand:
            if perception.pending_reference == investigation.origin[1]:
                perception.clear_pending()
        elif self.pending is investigation:
            self.pending = None
        self.travelling = investigation if moving else None

    def compare(self, cues: tuple[Evidence, ...]) -> None:
        for account in self.accounts.values():
            original = account.delivery.testimony.cue
            if original.modality != "inspection" or account.compared is not None:
                continue
            for current in cues:
                if (current.modality == "inspection" and current.area == original.area
                        and current.label == original.label and current.at > original.at):
                    account.compared = ("locally consistent" if current.detail == original.detail
                                        else "locally different")
                    break

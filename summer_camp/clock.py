"""Integer simulation scheduling and caller-driven playback."""

from collections.abc import Callable
from fractions import Fraction
from heapq import heappop, heappush

DAY = 86_400
NORMAL_RATE = 16


class Clock:
    def __init__(self):
        self.now = 0
        self._sequence = 0
        self._events: list[tuple[int, int, Callable[[], None]]] = []

    def schedule(self, when: int, callback: Callable[[], None]) -> None:
        if type(when) is not int or when < self.now:
            raise ValueError("Schedule at an integer time at or after now")
        heappush(self._events, (when, self._sequence, callback))
        self._sequence += 1

    def advance(self, seconds: int) -> int:
        if type(seconds) is not int or seconds < 0:
            raise ValueError("Advance by a nonnegative integer number of seconds")
        target = self.now + seconds
        while self._events and self._events[0][0] <= target:
            self.now, _, callback = heappop(self._events)
            callback()
        self.now = target
        return seconds


class Playback:
    """Convert elapsed real time supplied by a host into integer simulation steps."""

    def __init__(self, advance: Callable[[int], int], rate: int | Fraction = NORMAL_RATE):
        self._advance = advance
        self._carry = Fraction(0)
        self.paused = False
        self.rate = rate

    @property
    def rate(self) -> Fraction:
        return self._rate

    @rate.setter
    def rate(self, value: int | Fraction) -> None:
        rate = Fraction(value)
        if rate <= 0:
            raise ValueError("Playback rate must be positive")
        self._rate = rate

    def update(self, elapsed: int | Fraction) -> int:
        """Return the simulated seconds applied by the advance callback."""
        elapsed = Fraction(elapsed)
        if elapsed < 0:
            raise ValueError("Elapsed time must be nonnegative")
        if self.paused or not elapsed:
            return 0
        total = self._carry + elapsed * self.rate
        seconds = int(total)
        applied = self._advance(seconds) if seconds else 0
        self._carry = total - seconds
        return applied

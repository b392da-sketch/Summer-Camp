"""The provisional, opt-in six-person M1 scenario."""

from .cognition import HOUR, Staff, StaffProfile
from .simulation import CampLayout, Scenario
from .world import MINUTE, Job

PATHS = {
    "commons": ("cabins", "kitchen", "workshop", "boathouse"),
    "cabins": ("commons",),
    "kitchen": ("commons",),
    "workshop": ("commons",),
    "boathouse": ("commons",),
}

JOBS = (
    Job("north cabin", "cabin", "cabins", 80 * MINUTE, "cabins"),
    Job("south cabin", "cabin", "cabins", 95 * MINUTE, "cabins"),
    Job("supply cart", "repair", "workshop", 110 * MINUTE, "repair"),
    Job("workshop shelf", "repair", "workshop", 85 * MINUTE, "repair"),
    Job("canoe rack", "repair", "boathouse", 105 * MINUTE, "repair"),
    Job("life jacket hooks", "repair", "boathouse", 70 * MINUTE, "repair"),
    *(Job(f"meal batch {number}", "cook", "kitchen", 100 * MINUTE, "cook", 3, 16)
      for number in range(1, 7)),
)


def reference_camp(days: int = 4) -> Scenario:
    roster = (
        ("Avery", "coordinator", ("cabins", "kitchen"), ("cabins", "cook"), 22, (0, 2, 5, 0)),
        ("Morgan", "cook", ("kitchen",), ("cook",), 21, (5, 0, 6, -2)),
        ("Robin", "maintenance", ("workshop",), ("repair",), 23, (-2, -2, 6, 0)),
        ("Cameron", "waterfront", ("boathouse",), ("repair",), 22, (0, 0, 5, 4)),
        ("Jordan", "counselor", ("cabins",), ("cabins", "cook"), 23, (1, -2, 0, 6)),
        ("Taylor", "counselor", ("cabins",), ("cabins",), 21, (-2, 3, -2, 8)),
    )
    staff = tuple(
        Staff(name, "commons", preferences=preferences,
              profile=StaffProfile(role, duties, skills, bed * HOUR,
                                   (450 + 15 * (index % 3)) * MINUTE))
        for index, (name, role, duties, skills, bed, preferences) in enumerate(roster)
    )
    return Scenario(staff=staff, days=days, servings=16, camp=CampLayout(PATHS, JOBS, 18))

"""The provisional, opt-in six-person M1 scenario."""

from dataclasses import replace

from .cognition import HOUR, Staff, StaffProfile
from .ecology import Ecology, Trail
from .perception import Environment, Fitting, Link
from .simulation import CampLayout, Scenario
from .social import SocialProfile
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


def social_camp(days: int = 4) -> Scenario:
    camp = reference_camp(days)
    temperaments = ((1, 0), (0, 1), (-3, 1), (1, 1), (2, 0), (-1, -1))
    profiles = tuple(
        (staff.name, SocialProfile(company, helpfulness, ("Morgan",) if index == 0 else ()))
        for index, (staff, (company, helpfulness)) in enumerate(zip(camp.staff, temperaments))
    )
    return replace(camp, social=profiles)


def perception_camp(days: int = 4) -> Scenario:
    camp = social_camp(days)
    paths = {
        **PATHS,
        "commons": ("cabins", "kitchen", "workshop", "shore path", "woodland"),
        "boathouse": ("shore path",),
        "shore path": ("commons", "boathouse"),
        "woodland": ("commons",),
    }
    assert camp.camp is not None
    layout = replace(camp.camp, paths=paths)
    environment = Environment(
        fittings=(Fitting("shelter shutter", "shutter", "commons"),),
        acoustic=(
            Link("commons", "kitchen", 3), Link("commons", "workshop", 5),
            Link("commons", "cabins", 7), Link("commons", "woodland", 6),
            Link("commons", "boathouse", 4), Link("boathouse", "shore path", 2),
        ),
        sightlines=(Link("commons", "shore path", 1),),
        lamps=(("commons", 3),),
        curiosity=(("Avery", 22), ("Morgan", 19), ("Cameron", 21), ("Jordan", 14)),
        nightly_target="shelter shutter",
    )
    return replace(camp, camp=layout, environment=environment)


def witness_camp(days: int = 4) -> Scenario:
    camp = perception_camp(days)
    profiles = tuple((name, replace(profile, company=1) if name == "Taylor" else profile)
                     for name, profile in camp.social)
    return replace(camp, social=profiles, witness_reports=True)

def ecology_camp(days: int = 4) -> Scenario:
    camp = witness_camp(days)
    assert camp.camp is not None and camp.environment is not None
    paths = {**camp.camp.paths, "kitchen": ("commons", "service yard"),
             "service yard": ("kitchen", "woodland"), "woodland": ("commons", "service yard")}
    fitting = camp.environment.fittings[0]
    job = Job("secure shelter shutter", "secure", fitting.location, 45 * MINUTE,
              "repair", fitting=fitting.key)
    layout = replace(camp.camp, paths=paths, jobs=(*camp.camp.jobs, job))
    environment = replace(
        camp.environment, nightly_target=None,
        acoustic=(*camp.environment.acoustic, Link("kitchen", "service yard", 2)),
        lamps=(*camp.environment.lamps, ("service yard", 2)),
    )
    ecology = Ecology(("commons", "woodland", "shore path", "service yard"), fitting.key,
                      "woodland", "service yard", (Trail("woodland", "service yard"),))
    return replace(camp, camp=layout, environment=environment, ecology=ecology)

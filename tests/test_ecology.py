"""Physical preconditions, autonomous offscreen ecology, and sensory boundaries."""

from dataclasses import replace
import unittest

from summer_camp.clock import DAY, Playback
from summer_camp.cognition import Staff, StaffProfile
from summer_camp.ecology import ANIMAL_INTERVAL, WEATHER_INTERVAL, Trail
from summer_camp.perception import HOUR, INSPECTION_TIME, MINUTE, Environment, Fitting, Link
from summer_camp.reference_camp import ecology_camp
from summer_camp.simulation import CampLayout, Scenario, Simulation
from summer_camp.social import Exchange, SocialProfile
from summer_camp.world import Job, Request

BASE = ecology_camp()
PATHS = BASE.camp.paths
SHUTTER = Fitting("private shutter key", "shutter", "commons")
COOK = Job("stew batch", "cook", "kitchen", 5 * MINUTE, "cook", ingredients=2, produces=4)


def person(name, location, *, skills=(), needs=(0, 0, 0, 0)):
    return Staff(name, location, needs, (0, 0, -100, 0), StaffProfile("test", capabilities=skills))


def fixture(*staff, jobs=(), loose=True, accessible=True, raining=False, acoustic=(), curiosity=(),
            sound_fixture=SHUTTER, witness_reports=False):
    item = replace(sound_fixture, loose=loose)
    environment = Environment((item,), acoustic=acoustic,
                              lamps=((item.location, 3),) if item.location == "service yard"
                              else ((item.location, 3), ("service yard", 3)), curiosity=curiosity)
    ecology = replace(BASE.ecology, gust_target=item.key, refuse_accessible=accessible,
                      initial_raining=raining)
    social = tuple((member.name, SocialProfile(-1)) for member in staff) if witness_reports else ()
    return Scenario(staff, 1, 2, camp=CampLayout(PATHS, jobs, 2), social=social,
                    environment=environment, witness_reports=witness_reports, ecology=ecology)


def events(run, action, phase):
    return [event for event in run.history if (event.action, event.phase) == (action, phase)]


def evidence(run, staff):
    return [record["evidence"] for record in run.snapshot()["perception"][staff]["memory"]]


def secure(duration):
    return Job("secure shutter", "secure", "commons", duration, "repair", fitting=SHUTTER.key)


class EcologyTests(unittest.TestCase):
    def test_gust_is_suppressed_by_a_secured_fitting_and_removes_response(self):
        staff = person("Scout", "workshop")
        for loose in (False, True):
            with self.subTest(loose=loose):
                scenario = fixture(staff, loose=loose, acoustic=(Link("commons", "workshop", 4),),
                                   curiosity=(("Scout", 35),))
                run = Simulation(scenario, seed=0)
                run.advance(WEATHER_INTERVAL + 30 * MINUTE)
                self.assertEqual(run.snapshot()["ecology"]["wind"], "gusty")
                self.assertEqual(run.snapshot()["fitting_positions"][SHUTTER.key], loose)
                self.assertEqual(bool(events(run, "disturbance", "occurred")), loose)
                self.assertEqual(bool(events(run, "inspect", "completed")), loose)

    def test_securement_completion_order_and_manual_disturbance(self):
        worker = person("Worker", "commons", skills=("repair",))
        for relative in (-1, 0, 1):
            with self.subTest(relative=relative):
                job = secure(WEATHER_INTERVAL + relative)
                run = Simulation(fixture(worker, jobs=(job,)), seed=0)
                self.assertTrue(run.submit("Worker", Request("prepare", target=job.target)))
                run.queue_disturbance(WEATHER_INTERVAL + 2, SHUTTER.key, "manual impulse")
                run.advance(WEATHER_INTERVAL + 2)
                self.assertTrue(run.snapshot()["fitting_security"][SHUTTER.key])
                self.assertEqual(run.snapshot()["job_states"][job.target], "secured")
                self.assertEqual(len(events(run, "disturbance", "occurred")), int(relative >= 0))
                self.assertTrue(run.submit("Worker", Request("inspect")))
                run.advance(INSPECTION_TIME)
                self.assertEqual(evidence(run, "Worker")[-1]["detail"], "secure latch")
                self.assertEqual(run.snapshot()["fitting_positions"][SHUTTER.key], relative >= 0)

    def test_cancellation_and_interruption_do_not_secure_the_shutter(self):
        job = secure(45 * MINUTE)
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                needs = (81, 0, 0, 0) if interrupted else (0, 0, 0, 0)
                worker = person("Worker", "commons", skills=("repair",), needs=needs)
                run = Simulation(fixture(worker, jobs=(job,)), seed=0)
                self.assertTrue(run.submit("Worker", Request("prepare", target=job.target)))
                run.advance(15 * MINUTE)
                if interrupted:
                    self.assertTrue(events(run, "prepare", "interrupted"))
                else:
                    self.assertTrue(run.cancel_preparation("Worker"))
                self.assertFalse(run.snapshot()["fitting_security"][SHUTTER.key])
                self.assertEqual(run.snapshot()["job_states"][job.target], "pending")
                run.queue_disturbance(run.now + 1, SHUTTER.key, "manual impulse")
                run.advance(1)
                self.assertTrue(run.snapshot()["fitting_positions"][SHUTTER.key])

    def test_rain_persists_then_drains_and_can_be_observed_later(self):
        run = Simulation(fixture(person("Scout", "commons"), raining=True), seed=4)
        run.advance(WEATHER_INTERVAL - 1)
        self.assertEqual(run.snapshot()["ecology"]["wetness"]["commons"], 0)
        run.advance(1)
        self.assertEqual((run.snapshot()["ecology"]["raining"],
                          run.snapshot()["ecology"]["wetness"]["commons"]), (True, 2))
        run.advance(WEATHER_INTERVAL)
        self.assertEqual((run.snapshot()["ecology"]["raining"],
                          run.snapshot()["ecology"]["wetness"]["commons"]), (False, 4))
        run.advance(WEATHER_INTERVAL)
        self.assertEqual(run.snapshot()["ecology"]["wetness"]["commons"], 3)
        timeline = events(run, "weather", "updated")
        self.assertEqual([event.at for event in timeline], [3 * HOUR, 6 * HOUR, 9 * HOUR])
        scout = Simulation(fixture(person("Scout", "commons"), raining=True), seed=4)
        scout.advance(WEATHER_INTERVAL)
        self.assertTrue(scout.submit("Scout", Request("inspect")))
        scout.advance(INSPECTION_TIME)
        self.assertIn("wet ground", [cue["detail"] for cue in evidence(scout, "Scout")])

    def test_offscreen_foraging_arrival_persistence_and_stale_callback(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        for accessible in (True, False):
            with self.subTest(accessible=accessible):
                run = Simulation(fixture(cook, jobs=(COOK,), accessible=accessible), seed=0)
                self.assertTrue(run.submit("Cook", Request("prepare", target=COOK.target)))
                run.advance(COOK.duration)
                self.assertEqual(run.snapshot()["ecology"]["scraps"], 2)
                for location in ("commons", "cabins"):
                    self.assertTrue(run.submit("Cook", Request("move", location)))
                    run.advance(10 * MINUTE)
                self.assertTrue(run.submit("Cook", Request("sleep")))
                run.advance(ANIMAL_INTERVAL - run.now)
                state = run.snapshot()["ecology"]["raccoon"]
                if not accessible:
                    self.assertEqual((state["location"], state["transit"]), ("woodland", None))
                    run.advance(HOUR)
                    self.assertFalse(events(run, "forage", "completed"))
                    self.assertFalse(run.snapshot()["ecology"]["tipped"])
                    continue
                self.assertIsNone(state["location"])
                self.assertEqual(state["transit"], {"origin": "woodland", "destination": "service yard",
                                                    "arrival": 40 * MINUTE})
                trip = run._world.ecology.raccoon.transit
                run._clock.schedule(trip.arrival, lambda: run._animal_arrival(trip))
                run.advance(10 * MINUTE - 1)
                self.assertFalse(run.snapshot()["ecology"]["tipped"])
                run.advance(1)
                self.assertEqual(len(events(run, "wildlife travel", "completed")), 1)
                self.assertEqual(run.snapshot()["ecology"]["scraps"], 1)
                self.assertTrue(run.snapshot()["ecology"]["tipped"])
                self.assertEqual(evidence(run, "Cook"), [])
                run.advance(2 * HOUR)
                self.assertEqual(run.snapshot()["ecology"]["scraps"], 0)
                self.assertEqual(len(events(run, "disturbance", "occurred")), 1)
                self.assertTrue(run.snapshot()["ecology"]["tipped"])
                self.assertEqual((run.snapshot()["ingredients"], run.snapshot()["servings"]), (0, 6))

    def test_empty_refuse_keeps_animal_at_den_and_cancelled_cooking_creates_no_scraps(self):
        run = Simulation(fixture(person("Cook", "kitchen", skills=("cook",)), jobs=(COOK,)))
        self.assertTrue(run.submit("Cook", Request("prepare", target=COOK.target)))
        run.advance(MINUTE)
        self.assertTrue(run.cancel_preparation("Cook"))
        run.advance(HOUR)
        self.assertEqual(run.snapshot()["ecology"]["raccoon"]["location"], "woodland")
        self.assertEqual(run.snapshot()["ecology"]["scraps"], 0)
        self.assertFalse(events(run, "wildlife travel", "started"))

    def test_wildlife_route_traverses_only_configured_timed_legs(self):
        scenario = fixture(person("Cook", "kitchen", skills=("cook",)), jobs=(COOK,))
        ecology = replace(scenario.ecology, trails=(Trail("woodland", "shore path", 4 * MINUTE),
                                                    Trail("shore path", "service yard", 6 * MINUTE)))
        run = Simulation(replace(scenario, ecology=ecology))
        self.assertTrue(run.submit("Cook", Request("prepare", target=COOK.target)))
        run.advance(34 * MINUTE)
        self.assertEqual(run.snapshot()["ecology"]["raccoon"]["location"], "shore path")
        self.assertFalse(events(run, "forage", "completed"))
        run.advance(36 * MINUTE - 1)
        self.assertIsNone(run.snapshot()["ecology"]["raccoon"]["location"])
        run.advance(1)
        self.assertEqual([event.detail for event in events(run, "wildlife travel", "completed")],
                         ["shore path", "service yard"])
        self.assertEqual(len(events(run, "forage", "completed")), 1)

    def test_indistinct_sounds_match_and_visible_observer_can_identify_animal(self):
        fitting = replace(SHUTTER, location="service yard")
        acoustic = (Link("service yard", "kitchen", 6),)
        observer = person("Scout", "kitchen")
        visible = person("Visible", "service yard")
        cook = person("Cook", "kitchen", skills=("cook",))
        scenario = fixture(observer, visible, cook, jobs=(COOK,), sound_fixture=fitting, acoustic=acoustic)
        animal = Simulation(scenario)
        self.assertTrue(animal.submit("Cook", Request("prepare", target=COOK.target)))
        animal.advance(40 * MINUTE)
        wind = Simulation(scenario)
        wind.queue_disturbance(40 * MINUTE, fitting.key, "gust")
        wind.advance(40 * MINUTE)
        self.assertEqual(evidence(animal, "Scout"), evidence(wind, "Scout"))
        self.assertEqual(evidence(animal, "Scout"), [
            {"at": 40 * MINUTE, "modality": "sound", "detail": "indistinct noise", "area": None, "label": None},
        ])
        self.assertEqual(evidence(animal, "Visible")[0]["label"], "raccoon")
        self.assertEqual(evidence(wind, "Visible")[0]["label"], "shutter")
        self.assertIn("raccoon contact", events(animal, "disturbance", "occurred")[0].detail)
        self.assertIn("gust", events(wind, "disturbance", "occurred")[0].detail)

    def test_later_inspection_and_testimony_preserve_only_perceptible_features(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        scout = person("Scout", "kitchen")
        other = person("Listener", "commons")
        scenario = fixture(cook, scout, other, jobs=(COOK,), witness_reports=True,
                           acoustic=(Link("service yard", "kitchen", 6),))
        run = Simulation(scenario)
        self.assertTrue(run.submit("Cook", Request("prepare", target=COOK.target)))
        run.advance(40 * MINUTE)
        self.assertTrue(run.submit("Scout", Request("move", "commons")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Scout", Exchange("Listener", "testimony", reference=1)))
        run.advance(5 * MINUTE)
        claim = run.snapshot()["testimony"]["Listener"]["accounts"][("Scout", 1)]["delivery"]
        self.assertEqual(claim["testimony"]["observation"]["evidence"]["detail"], "indistinct noise")
        self.assertNotIn("raccoon", repr(claim))
        self.assertNotIn("service yard", repr(claim))
        for location in ("kitchen", "service yard"):
            self.assertTrue(run.submit("Listener", Request("move", location)))
            run.advance(10 * MINUTE)
        self.assertTrue(run.submit("Listener", Request("inspect")))
        run.advance(INSPECTION_TIME)
        self.assertEqual(evidence(run, "Listener")[-1]["detail"], "tipped container")
        self.assertNotIn("raccoon", repr(evidence(run, "Listener")))

    def test_controlled_wind_and_foraging_trace_with_later_discovery(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        scout = person("Scout", "workshop")
        camp = fixture(cook, scout, jobs=(COOK,), curiosity=(("Scout", 35),),
                       acoustic=(Link("kitchen", "service yard", 2), Link("workshop", "commons", 4)))
        run = Simulation(camp, seed=0)
        self.assertTrue(run.submit("Cook", Request("prepare", target=COOK.target)))
        run.advance(COOK.duration)
        for location in ("commons", "cabins"):
            self.assertTrue(run.submit("Cook", Request("move", location)))
            run.advance(10 * MINUTE)
        self.assertTrue(run.submit("Cook", Request("sleep")))
        run.advance(40 * MINUTE - run.now)
        self.assertTrue(run.snapshot()["ecology"]["tipped"])
        self.assertEqual(evidence(run, "Cook"), [])
        self.assertEqual(evidence(run, "Scout"), [])

        run.advance(3 * HOUR + 15 * MINUTE - run.now)
        cues = evidence(run, "Scout")
        self.assertEqual([cue["detail"] for cue in cues], ["clatter", "loose latch"])
        self.assertIsNone(cues[0]["label"])
        self.assertIn("investigate:commons", events(run, "move", "started")[-1].detail)
        for location in ("kitchen", "service yard"):
            self.assertTrue(run.submit("Scout", Request("move", location)))
            run.advance(10 * MINUTE)
        self.assertTrue(run.submit("Scout", Request("inspect")))
        run.advance(INSPECTION_TIME)
        self.assertEqual(evidence(run, "Scout")[-1]["detail"], "tipped container")
        self.assertNotIn("raccoon", repr(evidence(run, "Scout")))

    def test_reference_replay_food_and_normal_activity(self):
        camp = ecology_camp()
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                whole = Simulation(camp, seed=seed)
                stepped = Simulation(camp, seed=seed)
                whole.advance(4 * DAY)
                while stepped.now < stepped.horizon:
                    stepped.advance(2137)
                self.assertEqual(whole.history, stepped.history)
                self.assertEqual(whole.snapshot(), stepped.snapshot())
                self.assertTrue(events(whole, "weather", "updated"))
                self.assertTrue(events(whole, "wildlife", "decided"))
                self.assertTrue(events(whole, "social", "completed"))
                for staff in camp.staff:
                    completed = [event.action for event in whole.history if event.staff == staff.name
                                 and event.phase == "completed"]
                    self.assertIn(completed.count("meal"), range(8, 17))
                    self.assertIn(completed.count("sleep"), range(3, 5))
                    self.assertIn("leisure", completed)
                state = whole.snapshot()
                self.assertIn("repaired", state["job_states"].values())
                batches = [job for job in camp.camp.jobs if state["job_states"][job.target] == "cooked"]
                self.assertTrue(batches)
                self.assertEqual(state["ingredients"], camp.camp.ingredients - sum(job.ingredients for job in batches))
                self.assertEqual(state["servings"], camp.servings + sum(job.produces for job in batches)
                                 - len(events(whole, "meal", "started")))
                self.assertGreaterEqual(state["ingredients"], state["reserved_ingredients"])
                self.assertGreaterEqual(state["servings"], 0)
                self.assertIn(state["ecology"]["scraps"], range(7))

    def test_seven_day_horizon_and_playback(self):
        run = Simulation(ecology_camp(days=7))
        self.assertEqual(Playback(run.advance).update(60), 16 * 60)
        run.advance(8 * DAY)
        self.assertEqual(run.now, 7 * DAY)
        self.assertEqual(events(run, "weather", "updated")[-1].at, 7 * DAY)
        self.assertFalse(any(event.at == 7 * DAY for event in events(run, "disturbance", "occurred")))

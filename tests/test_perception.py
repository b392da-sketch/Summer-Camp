"""Spatial evidence, ordered physical transitions, and autonomous inspection."""

from dataclasses import replace
import unittest

from summer_camp.clock import DAY, Playback
from summer_camp.cognition import Staff, StaffProfile
from summer_camp.perception import (
    CUE_LIFETIME, HOUR, INSPECTION_TIME, MEMORY_SIZE, MINUTE,
    Environment, Evidence, Fitting, Link, PhysicalEvent, project, sound_distances,
)
from summer_camp.reference_camp import PATHS, perception_camp
from summer_camp.simulation import CampLayout, Scenario, Simulation
from summer_camp.world import Job, Request


SHUTTER = Fitting("internal fitting id", "shutter", "boathouse")


def person(name, location, *, needs=(0, 0, 0, 0)):
    return Staff(name, location, needs, (0, 0, 0, 0), StaffProfile("test"))


def scenario(*staff, environment, paths=PATHS):
    return Scenario(staff, 1, 20, camp=CampLayout(paths, (), 0), environment=environment)


def observed(run, staff):
    return run.snapshot()["perception"][staff]["memory"]


def events(run, action, phase):
    return [event for event in run.history if (event.action, event.phase) == (action, phase)]


class PerceptionTests(unittest.TestCase):
    def test_light_sightline_and_attention_change_detail_without_changing_event(self):
        physical = PhysicalEvent(21 * HOUR, SHUTTER, "gust", True)
        environment = Environment(
            (SHUTTER,), acoustic=(Link("boathouse", "commons", 3),),
            sightlines=(Link("boathouse", "commons", 2),), lamps=(("boathouse", 3),),
        )
        distances = sound_distances("boathouse", environment.acoustic)
        lit = project(physical, environment, "boathouse", distances)
        self.assertEqual(lit[0], Evidence(physical.at, "vision", "moving", "boathouse", "shutter"))
        dark = project(physical, replace(environment, lamps=()), "boathouse", distances)
        self.assertEqual(dark, (lit[1],))
        obstructed = project(physical, environment, "commons", distances)
        self.assertEqual(obstructed[0], Evidence(physical.at, "vision", "motion", "boathouse"))
        focused = project(physical, environment, "commons", distances, focused=True)
        self.assertEqual(focused, (obstructed[1],))
        no_sightline = project(physical, replace(environment, sightlines=()), "commons", distances)
        self.assertEqual(no_sightline, focused)

    def test_acoustic_links_differ_from_routes_and_tied_directions_are_withheld(self):
        fixture = replace(SHUTTER, strength=9)
        edges = (Link("boathouse", "commons", 2), Link("boathouse", "workshop", 3),
                 Link("commons", "kitchen", 2), Link("workshop", "kitchen", 1),
                 Link("commons", "cabins", 6))
        paths = {**PATHS, "boathouse": ("workshop",),
                 "workshop": ("commons", "boathouse"),
                 "commons": ("cabins", "kitchen", "workshop")}
        environment = Environment((fixture,), acoustic=edges)
        run = Simulation(scenario(person("Alex", "commons"), person("Bo", "kitchen"),
                                  person("Casey", "cabins"), environment=environment, paths=paths))
        self.assertFalse(run.submit("Alex", Request("move", "boathouse")))
        run.queue_disturbance(0, fixture.key, "gust")
        run.advance(0)
        self.assertEqual(observed(run, "Alex")[0]["evidence"]["area"], "boathouse")
        evidence = observed(run, "Bo")[0]["evidence"]
        self.assertEqual((evidence["detail"], evidence["area"]), ("clatter", None))
        self.assertEqual(observed(run, "Casey"), [])
        # Attending elsewhere can put a marginal signal below threshold.
        physical = PhysicalEvent(0, fixture, "gust", True)
        narrow = (Link("boathouse", "cabins", 7),)
        distances = sound_distances("boathouse", narrow)
        limited = replace(environment, acoustic=narrow)
        self.assertEqual(project(physical, limited, "cabins", distances)[0].detail, "indistinct noise")
        self.assertFalse(project(physical, limited, "cabins", distances, focused=True))

    def test_sleep_and_transit_do_not_receive_cues_or_replay_them_on_arrival(self):
        environment = Environment((SHUTTER,), acoustic=(Link("boathouse", "cabins", 1),),
                                  lamps=(("boathouse", 3),))
        run = Simulation(scenario(person("Asleep", "cabins"), person("Walking", "commons"),
                                  environment=environment))
        self.assertTrue(run.submit("Asleep", Request("sleep")))
        self.assertTrue(run.submit("Walking", Request("move", "boathouse")))
        run.queue_disturbance(MINUTE, SHUTTER.key, "gust")
        run.advance(10 * MINUTE)
        self.assertEqual(run.snapshot()["locations"]["Walking"], "boathouse")
        self.assertEqual(observed(run, "Asleep"), [])
        self.assertEqual(observed(run, "Walking"), [])
        self.assertTrue(run.submit("Walking", Request("inspect")))
        run.advance(INSPECTION_TIME)
        inspection, = observed(run, "Walking")
        self.assertEqual(inspection["evidence"]["detail"], "loose latch")
        self.assertEqual(inspection["evidence"]["at"], 15 * MINUTE)
        self.assertNotIn("gust", repr(inspection))

    def test_different_objective_causes_produce_identical_beliefs(self):
        environment = Environment((SHUTTER,), acoustic=(Link("boathouse", "commons", 4),))
        results = []
        for cause in ("gust", "falling twig"):
            run = Simulation(scenario(person("Alex", "commons"), environment=environment))
            run.queue_disturbance(0, SHUTTER.key, cause)
            run.advance(0)
            physical, = events(run, "disturbance", "occurred")
            self.assertIn(f"cause={cause}", physical.detail)
            evidence, = observed(run, "Alex")
            self.assertEqual(evidence["evidence"], {
                "at": 0, "modality": "sound", "detail": "clatter", "area": "boathouse", "label": None,
            })
            self.assertNotIn(cause, repr(evidence))
            self.assertNotIn(SHUTTER.key, repr(evidence))
            results.append(evidence)
        self.assertEqual(*results)

    def test_dispositions_change_response_without_interrupting_leisure(self):
        environment = Environment((SHUTTER,), acoustic=(Link("boathouse", "commons", 3),),
                                  lamps=(("boathouse", 3),), curiosity=(("Alex", 35),))
        run = Simulation(scenario(person("Alex", "commons", needs=(0, 0, 0, 40)),
                                  person("Bo", "commons", needs=(0, 0, 0, 40)),
                                  environment=environment))
        run.queue_disturbance(30 * MINUTE, SHUTTER.key, "gust")
        run.advance(54 * MINUTE)
        self.assertEqual(observed(run, "Alex"), observed(run, "Bo"))
        self.assertFalse(events(run, "leisure", "completed"))
        self.assertFalse(events(run, "move", "started"))
        run.advance(MINUTE)
        self.assertEqual(len(events(run, "leisure", "completed")), 2)
        move, = events(run, "move", "started")
        self.assertEqual((move.staff, move.at), ("Alex", 55 * MINUTE))
        run.advance(10 * MINUTE - 1)
        self.assertFalse(events(run, "inspect", "started"))
        self.assertEqual(run.snapshot()["locations"]["Alex"], "commons")
        run.advance(1)
        started, = events(run, "inspect", "started")
        self.assertEqual((started.staff, started.at), ("Alex", 65 * MINUTE))
        run.advance(INSPECTION_TIME)
        self.assertEqual(observed(run, "Alex")[-1]["evidence"]["detail"], "loose latch")
        self.assertEqual(len(observed(run, "Bo")), 1)
        self.assertIsNone(run.snapshot()["perception"]["Alex"]["pending"])

    def test_expired_cue_cannot_trigger_trip_and_memory_remains_bounded(self):
        environment = Environment((SHUTTER,), acoustic=(Link("boathouse", "workshop", 3),),
                                  curiosity=(("Alex", 35),))
        alex = person("Alex", "workshop")
        alex = replace(alex, profile=replace(alex.profile, capabilities=("repair",)))
        fixture = scenario(alex, environment=environment)
        job = Job("shelf", "repair", "workshop", CUE_LIFETIME + MINUTE, "repair")
        fixture = replace(fixture, camp=replace(fixture.camp, jobs=(job,)))
        run = Simulation(fixture)
        self.assertTrue(run.submit("Alex", Request("prepare", target="shelf")))
        for index in range(MEMORY_SIZE + 2):
            run.queue_disturbance(index, SHUTTER.key, "gust")
        run.advance(job.duration)
        self.assertEqual(len(observed(run, "Alex")), MEMORY_SIZE)
        self.assertIsNone(run.snapshot()["perception"]["Alex"]["pending"])
        self.assertFalse(events(run, "move", "started"))
        self.assertFalse(events(run, "inspect", "started"))

    def test_inspection_can_be_inconclusive(self):
        environment = Environment((SHUTTER,), acoustic=(Link("boathouse", "commons", 3),),
                                  curiosity=(("Alex", 35),))
        run = Simulation(scenario(person("Alex", "commons"), environment=environment))
        run.queue_disturbance(0, SHUTTER.key, "gust")
        run.advance(35 * MINUTE)
        finished, = events(run, "inspect", "completed")
        self.assertEqual(finished.detail, "inconclusive")
        self.assertEqual(len(observed(run, "Alex")), 1)
        run.advance(30 * MINUTE)
        self.assertEqual(len(events(run, "inspect", "started")), 1)

    def test_order_of_arrival_waking_and_physical_event_at_same_time(self):
        environment = Environment((SHUTTER,), lamps=(("boathouse", 3),))
        for arrives_first in (True, False):
            with self.subTest(arrives_first=arrives_first):
                run = Simulation(scenario(person("Alex", "commons"), environment=environment))
                if not arrives_first:
                    run.queue_disturbance(10 * MINUTE, SHUTTER.key, "gust")
                self.assertTrue(run.submit("Alex", Request("move", "boathouse")))
                if arrives_first:
                    run.queue_disturbance(10 * MINUTE, SHUTTER.key, "gust")
                run.advance(10 * MINUTE)
                self.assertEqual(bool(observed(run, "Alex")), arrives_first)

        fitting = replace(SHUTTER, location="cabins")
        environment = replace(environment, fittings=(fitting,), lamps=(("cabins", 3),))
        for wakes_first in (True, False):
            with self.subTest(wakes_first=wakes_first):
                alex = person("Alex", "cabins")
                alex = replace(alex, profile=replace(alex.profile, sleep_duration=4 * HOUR))
                run = Simulation(scenario(alex, environment=environment))
                self.assertTrue(run.submit("Alex", Request("sleep")))
                if wakes_first:
                    run.advance(4 * HOUR - 1)
                run.queue_disturbance(4 * HOUR, fitting.key, "gust")
                run.advance(4 * HOUR - run.now)
                self.assertEqual(bool(observed(run, "Alex")), wakes_first)

    def test_cancelled_or_blocked_transition_has_no_sensory_effect(self):
        secure = replace(SHUTTER, key="secured shutter", loose=False)
        environment = Environment((SHUTTER, secure), lamps=(("boathouse", 3),))
        run = Simulation(scenario(person("Alex", "boathouse"), environment=environment))
        key = run.queue_disturbance(MINUTE, SHUTTER.key, "gust")
        self.assertTrue(run.cancel_disturbance(key))
        self.assertFalse(run.cancel_disturbance(key))
        run.queue_disturbance(MINUTE, secure.key, "gust")
        run.advance(2 * MINUTE)
        self.assertEqual(observed(run, "Alex"), [])
        self.assertEqual(events(run, "disturbance", "occurred"), [])
        self.assertEqual(run.snapshot()["fitting_positions"], {SHUTTER.key: False, secure.key: False})

    def test_reference_camp_is_deterministic_and_preserves_ordinary_activity(self):
        fixture = perception_camp()
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                whole = Simulation(fixture, seed=seed)
                chunked = Simulation(fixture, seed=seed)
                whole.advance(4 * DAY)
                while chunked.now < chunked.horizon:
                    chunked.advance(2137)
                self.assertEqual(whole.history, chunked.history)
                self.assertEqual(whole.snapshot(), chunked.snapshot())
                self.assertEqual(len(events(whole, "disturbance", "occurred")), 4)
                self.assertTrue(events(whole, "vision", "perceived"))
                self.assertTrue(events(whole, "sound", "perceived"))
                self.assertTrue(events(whole, "inspect", "completed"))
                self.assertTrue(events(whole, "social", "completed"))
                for staff in fixture.staff:
                    performed = [event.action for event in whole.history
                                 if event.phase == "completed" and event.staff == staff.name]
                    self.assertIn(performed.count("meal"), range(8, 17))
                    self.assertIn(performed.count("sleep"), range(3, 5))
                    self.assertIn("leisure", performed)
                state = whole.snapshot()
                cooked = [job for job in fixture.camp.jobs if state["job_states"][job.target] == "cooked"]
                self.assertTrue(cooked)
                self.assertIn("ready", state["job_states"].values())
                self.assertIn("repaired", state["job_states"].values())
                self.assertEqual(state["ingredients"], fixture.camp.ingredients - sum(j.ingredients for j in cooked))
                self.assertEqual(state["servings"], fixture.servings + sum(j.produces for j in cooked)
                                 - len(events(whole, "meal", "started")))
                self.assertGreaterEqual(state["ingredients"], state["reserved_ingredients"])
                self.assertGreaterEqual(state["servings"], 0)

    def test_seven_day_horizon_and_normal_playback(self):
        run = Simulation(perception_camp(days=7))
        playback = Playback(run.advance)
        self.assertEqual(playback.update(60), 16 * 60)
        run.advance(8 * DAY)
        self.assertEqual(run.now, 7 * DAY)
        self.assertEqual(len(events(run, "disturbance", "occurred")), 7)

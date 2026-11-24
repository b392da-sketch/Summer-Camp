"""Behavioral and causal checks for the opt-in camp scenario."""

from collections import Counter
from dataclasses import replace
import unittest

from summer_camp.clock import DAY
from summer_camp.cognition import HOUR, Staff, StaffProfile
from summer_camp.reference_camp import PATHS, reference_camp
from summer_camp.simulation import CampLayout, Scenario, Simulation
from summer_camp.world import MINUTE, Job, Request


def worker(name="Alex", location="commons", *, duty=(), skills=(), needs=(0, 0, 0, 0),
           preferences=(0, 0, 0, 0), bedtime=22 * HOUR):
    return Staff(name, location, needs, preferences, StaffProfile("test", duty, skills, bedtime))


def camp(*staff, jobs=(), ingredients=0, servings=0, days=1):
    return Simulation(Scenario(staff, days, servings, camp=CampLayout(PATHS, jobs, ingredients)))


def batch(name="batch", duration=60 * MINUTE):
    return Job(name, "cook", "kitchen", duration, "cook", 2, 4)


def actions(run, phase, action):
    return [event for event in run.history if (event.phase, event.action) == (phase, action)]


def target(event):
    return event.detail.removeprefix("target=").split(" pending ->", 1)[0]


class CampLifeTests(unittest.TestCase):
    def test_inspection_discovers_work_and_hidden_state_cannot_redirect_early(self):
        alex = worker(duty=("boathouse",), skills=("repair",))
        rack = Job("rack", "repair", "boathouse", HOUR, "repair")
        damaged = camp(alex, jobs=(rack,))
        empty = camp(alex)
        for run in (damaged, empty):
            run.advance(10 * MINUTE - 1)
            self.assertNotIn("prepare:boathouse", run.snapshot()["minds"]["Alex"]["memory"])
        self.assertEqual(damaged.history, empty.history)
        for run in (damaged, empty):
            run.advance(1)
        self.assertEqual([target(event) for event in actions(damaged, "started", "prepare")], ["rack"])
        self.assertEqual(actions(empty, "started", "prepare"), [])
        self.assertEqual(empty.snapshot()["minds"]["Alex"]["memory"]["prepare:boathouse"]["jobs"], ())

    def test_responsibility_and_leisure_can_change_the_choice(self):
        rack = Job("rack", "repair", "boathouse", HOUR, "repair")
        obliged = worker(location="boathouse", duty=("boathouse",), skills=("repair",),
                          needs=(0, 0, 0, 54))
        unassigned = replace(obliged, profile=replace(obliged.profile, responsibilities=()))
        leisure = replace(obliged, preferences=(0, 0, 0, 15))
        for staff, expected in ((obliged, "prepare"), (unassigned, "move"), (leisure, "move")):
            with self.subTest(staff=staff):
                run = camp(staff, jobs=(rack,))
                run.advance(0)
                self.assertEqual(run.history[-1].action, expected)
                if expected == "move":
                    self.assertIn("goal=leisure", run.history[-1].detail)

    def test_location_and_capability_are_required(self):
        sign = Job("sign", "repair", "boathouse", HOUR, "repair")
        alex = worker(skills=("repair",))
        sam = worker("Sam", "boathouse")
        run = camp(alex, sam, jobs=(sign,))
        for name, reason in (("Alex", "wrong location"), ("Sam", "missing capability")):
            self.assertFalse(run.submit(name, Request("prepare", target="sign")))
            self.assertEqual(run.history[-1].detail, reason)
        self.assertEqual(run.snapshot()["job_states"], {"sign": "pending"})

    def test_cooking_interruption_releases_then_reserves_and_finishes_once(self):
        alex = worker(location="kitchen", duty=("kitchen",), skills=("cook",), needs=(81, 0, 0, 0))
        run = camp(alex, jobs=(batch(),), ingredients=2, servings=1)
        self.assertTrue(run.submit("Alex", Request("prepare", target="batch")))
        self.assertEqual(run.snapshot()["reserved_ingredients"], 2)
        run.advance(15 * MINUTE)
        state = run.snapshot()
        self.assertEqual((state["ingredients"], state["reserved_ingredients"], state["servings"]), (2, 0, 0))
        self.assertEqual(state["job_states"]["batch"], "pending")
        self.assertEqual(state["minds"]["Alex"]["preparations"],
                         {"batch": {"target": "batch", "remaining": 45 * MINUTE}})
        run.advance(25 * MINUTE)
        self.assertEqual(len(actions(run, "resumed", "prepare")), 1)
        self.assertEqual(run.snapshot()["reserved_ingredients"], 2)
        run.advance(45 * MINUTE - 1)
        self.assertEqual(run.snapshot()["servings"], 0)
        run.advance(1)
        state = run.snapshot()
        self.assertEqual((state["ingredients"], state["reserved_ingredients"], state["servings"]), (0, 0, 4))
        self.assertEqual(state["job_states"]["batch"], "cooked")
        self.assertFalse(run.submit("Alex", Request("prepare", target="batch")))
        self.assertEqual(len(actions(run, "completed", "prepare")), 1)

    def test_released_boathouse_slot_is_remembered_until_return_observation(self):
        alex = worker(location="boathouse", duty=("boathouse",), skills=("repair",),
                      needs=(81, 0, 0, 0))
        sam = worker("Sam", "boathouse", skills=("repair",), preferences=(0, 0, -100, 0))
        rack = Job("rack", "repair", "boathouse", 100 * MINUTE, "repair")
        free = camp(alex, sam, jobs=(rack,), servings=1)
        occupied = camp(alex, sam, jobs=(rack,), servings=1)
        for run in (free, occupied):
            self.assertTrue(run.submit("Alex", Request("prepare", target="rack")))
            run.advance(20 * MINUTE)
            interruption, = actions(run, "interrupted", "prepare")
            self.assertEqual(interruption.at, 15 * MINUTE)
        self.assertTrue(occupied.submit("Sam", Request("prepare", target="rack")))

        before_return = 80 * MINUTE - 1
        memories = []
        for run in (free, occupied):
            run.advance(before_return - run.now)
            memory = run.snapshot()["minds"]["Alex"]["memory"]["prepare:boathouse"]
            memories.append(memory)
            self.assertEqual(memory["at"], 15 * MINUTE)
            self.assertTrue(memory["jobs"][0]["available"])
            self.assertEqual(run.snapshot()["active"]["Alex"]["request"]["destination"], "boathouse")
        self.assertEqual(*memories)

        for run in (free, occupied):
            run.advance(1)
        resumption, = actions(free, "resumed", "prepare")
        self.assertEqual(resumption.at, 80 * MINUTE)
        self.assertEqual(free.snapshot()["active"]["Alex"]["ends_at"], 165 * MINUTE)
        self.assertEqual(actions(occupied, "resumed", "prepare"), [])
        self.assertFalse(occupied.submit("Alex", Request("prepare", target="rack")))
        self.assertEqual(occupied.history[-1].detail, "equipment occupied")

    def test_peer_can_complete_interrupted_batch_and_invalidate_commitment(self):
        alex = worker(location="kitchen", skills=("cook",), needs=(81, 0, 0, 0))
        sam = worker("Sam", "kitchen", skills=("cook",), preferences=(0, 0, -100, 0))
        run = camp(alex, sam, jobs=(batch(duration=20 * MINUTE),), ingredients=2, servings=1)
        self.assertTrue(run.submit("Alex", Request("prepare", target="batch")))
        run.advance(15 * MINUTE)
        self.assertTrue(run.submit("Sam", Request("prepare", target="batch")))
        run.advance(20 * MINUTE)
        self.assertEqual([event.staff for event in actions(run, "completed", "prepare")], ["Sam"])
        self.assertIn("batch", run.snapshot()["minds"]["Alex"]["preparations"])
        run.advance(5 * MINUTE)
        self.assertEqual([event.staff for event in actions(run, "abandoned", "prepare")], ["Alex"])
        self.assertNotIn("batch", run.snapshot()["minds"]["Alex"]["preparations"])
        self.assertEqual(run.snapshot()["servings"], 4)

    def test_resumption_revalidates_ingredients_used_by_another_batch(self):
        alex = worker(location="kitchen", skills=("cook",), needs=(81, 0, 0, 0))
        sam = worker("Sam", "kitchen", skills=("cook",), preferences=(0, 0, -100, 0))
        jobs = (batch("original"), batch("substitute", duration=20 * MINUTE))
        run = camp(alex, sam, jobs=jobs, ingredients=2, servings=1)
        self.assertTrue(run.submit("Alex", Request("prepare", target="original")))
        run.advance(15 * MINUTE)
        self.assertTrue(run.submit("Sam", Request("prepare", target="substitute")))
        run.advance(25 * MINUTE)
        self.assertFalse(run.submit("Alex", Request("prepare", target="original")))
        self.assertEqual(run.history[-1].detail, "insufficient unreserved ingredients")
        state = run.snapshot()
        self.assertEqual(state["job_states"], {"original": "pending", "substitute": "cooked"})
        self.assertEqual((state["ingredients"], state["servings"]), (0, 4))
        self.assertEqual(state["minds"]["Alex"]["preparations"],
                         {"original": {"target": "original", "remaining": 45 * MINUTE}})

    def test_simultaneous_cooks_get_one_slot_and_cancellation_releases_it(self):
        alex = worker(location="kitchen", duty=("kitchen",), skills=("cook",))
        sam = replace(alex, name="Sam")
        jobs = (batch("first"), batch("second"))
        for staff in ((alex, sam), (sam, alex)):
            with self.subTest(first=staff[0].name):
                run = camp(*staff, jobs=jobs, ingredients=2)
                run.advance(0)
                self.assertEqual([event.staff for event in actions(run, "started", "prepare")], [staff[0].name])
                self.assertFalse(run.submit(staff[1].name, Request("prepare", target="second")))
                self.assertEqual(run.history[-1].detail, "equipment occupied")
                self.assertTrue(run.cancel_preparation(staff[0].name))
                self.assertEqual(run.snapshot()["reserved_ingredients"], 0)
                self.assertTrue(run.submit(staff[1].name, Request("prepare", target="second")))
                run.advance(HOUR)
                self.assertEqual(run.snapshot()["job_states"], {"first": "pending", "second": "cooked"})
                self.assertEqual(run.snapshot()["ingredients"], 0)
                self.assertFalse(run.submit(staff[0].name, Request("prepare", target="first")))
                self.assertEqual(run.history[-1].detail, "insufficient unreserved ingredients")

    def test_sleep_recovers_over_time_and_preferences_shift_sleep_start(self):
        night = worker(location="cabins", needs=(0, 60, 0, 0), bedtime=0)
        noon = replace(night, profile=replace(night.profile, bedtime=12 * HOUR))
        early = camp(night)
        late = camp(noon)
        for run in (early, late):
            run.advance(0)
        self.assertEqual(len(actions(early, "started", "sleep")), 1)
        self.assertEqual(actions(late, "started", "sleep"), [])
        for hours, fatigue in ((2, 36), (4, 12)):
            early.advance(2 * HOUR)
            self.assertEqual(early.now, hours * HOUR)
            self.assertEqual(early.snapshot()["minds"]["Alex"]["needs"]["rest"], fatigue * HOUR)
            self.assertEqual(actions(early, "completed", "sleep"), [])
        early.advance(4 * HOUR)
        self.assertEqual(len(actions(early, "completed", "sleep")), 1)

    def test_sleeping_staff_observes_peer_completion_only_on_waking(self):
        sleeper = worker(location="cabins", needs=(0, 60, 0, 0), bedtime=0)
        peer = worker("Sam", "cabins", skills=("cabins",), preferences=(0, 0, -100, 0))
        cabin = Job("north cabin", "cabin", "cabins", HOUR, "cabins")
        run = camp(sleeper, peer, jobs=(cabin,))
        run.advance(0)
        self.assertEqual(len(actions(run, "started", "sleep")), 1)
        before_sleep = run.snapshot()["minds"]["Alex"]["memory"]
        self.assertFalse(before_sleep["prepare:cabins"]["jobs"][0]["done"])
        self.assertTrue(run.submit("Sam", Request("prepare", target="north cabin")))

        run.advance(2 * HOUR)
        state = run.snapshot()
        self.assertEqual(state["job_states"]["north cabin"], "ready")
        self.assertEqual(state["minds"]["Alex"]["needs"]["rest"], 36 * HOUR)
        self.assertEqual(state["minds"]["Alex"]["memory"], before_sleep)

        run.advance(6 * HOUR)
        woke, = actions(run, "completed", "sleep")
        self.assertEqual(woke.at, 8 * HOUR)
        observed = run.snapshot()["minds"]["Alex"]["memory"]["prepare:cabins"]
        self.assertEqual(observed["at"], woke.at)
        self.assertTrue(observed["jobs"][0]["done"])

    def test_empty_kitchen_does_not_cause_rapid_return_trips(self):
        alex = worker(duty=("kitchen",), skills=("cook",), needs=(90, 0, 0, 60))
        run = camp(alex, jobs=(batch(),))
        run.advance(DAY)
        arrivals = [event.at for event in actions(run, "completed", "move")
                    if event.detail == "kitchen"]
        self.assertGreaterEqual(len(arrivals), 2)
        self.assertTrue(all(b - a >= 2 * HOUR for a, b in zip(arrivals, arrivals[1:])))
        self.assertEqual(actions(run, "started", "prepare"), [])
        self.assertGreater(len(actions(run, "completed", "leisure")), 0)

    def test_four_day_runs_across_seeds_and_advance_chunking(self):
        scenario = reference_camp()
        histories = []
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                whole = Simulation(scenario, seed=seed)
                stepped = Simulation(scenario, seed=seed)
                whole.advance(4 * DAY)
                while stepped.now < stepped.horizon:
                    stepped.advance(2137)
                self.assertEqual(whole.history, stepped.history)
                self.assertEqual(whole.snapshot(), stepped.snapshot())
                histories.append(whole.history)

                counts = Counter((event.staff, event.action) for event in whole.history
                                 if event.phase == "completed")
                for staff in scenario.staff:
                    self.assertIn(counts[staff.name, "sleep"], range(3, 5))
                    self.assertIn(counts[staff.name, "meal"], range(8, 17))
                    self.assertGreater(counts[staff.name, "leisure"], 0)

                starts = [event.at % DAY for event in actions(whole, "started", "sleep")
                          if event.at >= 2 * DAY]
                self.assertGreater(len(starts), 0)
                evening = sum(hour >= 16 * HOUR or hour < 5 * HOUR for hour in starts)
                self.assertGreaterEqual(evening * 4, len(starts) * 3)

                completed = actions(whole, "completed", "prepare")
                targets = [target(event) for event in completed]
                self.assertEqual(len(targets), len(set(targets)))
                state = whole.snapshot()
                cooked = [job for job in scenario.camp.jobs if state["job_states"][job.target] == "cooked"]
                self.assertGreater(len(cooked), 0)
                self.assertIn("ready", state["job_states"].values())
                self.assertIn("repaired", state["job_states"].values())
                self.assertEqual(state["ingredients"], scenario.camp.ingredients - sum(j.ingredients for j in cooked))
                self.assertEqual(state["servings"], scenario.servings + sum(j.produces for j in cooked)
                                 - len(actions(whole, "started", "meal")))
                self.assertGreaterEqual(state["ingredients"], state["reserved_ingredients"])
                self.assertGreaterEqual(state["servings"], 0)
        self.assertEqual(len(set(histories)), len(histories))

    def test_opt_in_scenario_supports_seven_days(self):
        run = Simulation(reference_camp(days=7))
        run.advance(8 * DAY)
        self.assertEqual(run.now, 7 * DAY)

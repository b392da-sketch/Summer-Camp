"""Local observations, repeatable righting, and fixed departure-time travel."""

from dataclasses import replace
import unittest

from summer_camp.clock import DAY, Playback
from summer_camp.maintenance import RIGHTING_TIME
from summer_camp.perception import HOUR, INSPECTION_TIME, MINUTE
from summer_camp.reference_camp import maintenance_camp
from summer_camp.simulation import Simulation
from summer_camp.social import DURATION, Exchange
from summer_camp.world import Job, Request

from test_ecology import COOK, events, evidence, fixture, person


YARD = "service yard"
RIGHT = Request("right_bin")
BASE = maintenance_camp()
TIP = 40 * MINUTE
RETIP = 150 * MINUTE


def camp(*people, lamp=2, jobs=(COOK,), raining=False, testimony=False, curiosity=()):
    scenario = fixture(*people, jobs=jobs, raining=raining, witness_reports=testimony, curiosity=curiosity)
    environment = replace(
        scenario.environment, lamps=tuple((node, lamp if node == YARD else light)
                                          for node, light in scenario.environment.lamps),
    )
    return replace(scenario, environment=environment, camp=replace(scenario.camp, paths=BASE.camp.paths),
                   maintenance=BASE.maintenance)


def worker(name, location=YARD, *, eager=False, needs=(0, 0, 0, 0)):
    member = person(name, location, skills=("repair",), needs=needs)
    return replace(member, preferences=(0, 0, 10 if eager else -100, 0))


def start_cooking(run):
    assert run.submit("Cook", Request("prepare", target=COOK.target))


def ecostate(run):
    return run.snapshot()["ecology"]


def notices(run, staff):
    return [cue for cue in evidence(run, staff) if cue["modality"] == "notice"]


def memory(run, staff):
    return run.snapshot()["environmental_memory"][staff]


class MaintenanceTests(unittest.TestCase):
    def test_lit_local_noticing_is_private_and_deduplicated(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        for lamp in (0, 2):
            with self.subTest(lamp=lamp):
                run = Simulation(camp(cook, worker("Witness"), person("Away", "commons"), lamp=lamp))
                start_cooking(run)
                run.advance(55 * MINUTE)
                self.assertEqual(ecostate(run)["container_revision"], 1)
                self.assertEqual(evidence(run, "Away"), [])
                self.assertIsNone(memory(run, "Away")["checked"])
                self.assertEqual(len(notices(run, "Witness")), int(lamp > 0))
                if lamp:
                    self.assertEqual(memory(run, "Witness")["checked"],
                                     {"condition": "tipped container", "checked_at": 45 * MINUTE})
                else:
                    self.assertIsNone(memory(run, "Witness")["checked"])
                run.advance(10 * MINUTE)
                self.assertEqual(len(notices(run, "Witness")), int(lamp > 0))
                if lamp:
                    self.assertEqual(memory(run, "Witness")["checked"]["checked_at"], HOUR)

    def test_sleeping_travelling_and_focused_staff_do_not_notice(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        job = Job("bench check", "repair", YARD, 90 * MINUTE, "repair")
        run = Simulation(camp(cook, worker("Focused"), person("Traveller", YARD),
                              person("Sleeper", "cabins"), jobs=(COOK, job)))
        start_cooking(run)
        self.assertTrue(run.submit("Focused", Request("prepare", target=job.target)))
        self.assertTrue(run.submit("Sleeper", Request("sleep")))
        run.advance(35 * MINUTE)
        self.assertTrue(run.submit("Traveller", Request("move", "kitchen")))
        run.advance(15 * MINUTE)
        for name in ("Focused", "Traveller", "Sleeper"):
            self.assertEqual(notices(run, name), [])
        self.assertIsNone(memory(run, "Focused")["checked"])
        self.assertEqual(memory(run, "Traveller")["checked"]["condition"], "upright container")
        self.assertIsNone(memory(run, "Sleeper")["checked"])

    def test_completion_cancellation_competition_and_stale_action(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        run = Simulation(camp(cook, worker("Morgan"), worker("Jordan"), person("Visitor", YARD)))
        start_cooking(run)
        run.advance(TIP)
        self.assertFalse(run.submit("Visitor", RIGHT))
        self.assertFalse(run.submit("Cook", RIGHT))
        self.assertTrue(run.submit("Morgan", RIGHT))
        old = run._world.active["Morgan"]
        self.assertFalse(run.submit("Jordan", RIGHT))
        run.advance(MINUTE)
        self.assertTrue(run.cancel_maintenance("Morgan"))
        self.assertTrue(ecostate(run)["tipped"])
        self.assertEqual(ecostate(run)["container_revision"], 1)
        self.assertIsNone(run.snapshot()["righting"])
        self.assertTrue(run.submit("Jordan", RIGHT))
        reservation = run.snapshot()["righting"]
        self.assertEqual((reservation["worker"], reservation["revision"]), ("Jordan", 1))
        self.assertNotEqual(reservation["ticket"], old.reservation.ticket)
        run._clock.schedule(old.ends_at, lambda: self.assertFalse(
            run._world.complete_righting("Morgan", old, run.now)))
        run.advance(RIGHTING_TIME - MINUTE)
        self.assertEqual(run.snapshot()["righting"], reservation)
        run.advance(MINUTE)
        self.assertFalse(ecostate(run)["tipped"])
        self.assertEqual(ecostate(run)["container_revision"], 2)
        self.assertIsNone(run.snapshot()["righting"])
        self.assertFalse(run.submit("Jordan", RIGHT))
        self.assertEqual(len(events(run, "right_bin", "completed")), 1)

    def test_interruption_resumes_only_current_revision(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        for intervened in (False, True):
            with self.subTest(intervened=intervened):
                run = Simulation(camp(cook, worker("Morgan", needs=(74, 0, 0, 0)), worker("Jordan")))
                # Keep the hungry worker idle before the controlled start.
                run._wakes.pop("Morgan")
                start_cooking(run)
                run.advance(TIP)
                self.assertTrue(run.submit("Morgan", RIGHT))
                run.advance(15 * MINUTE)
                self.assertEqual(memory(run, "Morgan")["progress"], {"revision": 1, "remaining": 15 * MINUTE})
                self.assertIsNone(run.snapshot()["righting"])
                if intervened:
                    self.assertTrue(run.submit("Jordan", RIGHT))
                return_at = RETIP if intervened else 90 * MINUTE
                run.advance(return_at - run.now)
                self.assertTrue(run.submit("Morgan", Request("move", YARD)))
                run.advance(10 * MINUTE)
                if intervened:
                    self.assertEqual(ecostate(run)["container_revision"], 3)
                    self.assertFalse(run.submit("Morgan", RIGHT))
                    self.assertEqual(run.history[-1].detail, "Obsolete righting progress")
                    self.assertTrue(run.submit("Morgan", RIGHT))
                    self.assertEqual(run.snapshot()["active"]["Morgan"]["ends_at"] - run.now, RIGHTING_TIME)
                else:
                    self.assertTrue(run.submit("Morgan", RIGHT))
                    self.assertEqual(run.history[-1].phase, "resumed")
                    self.assertEqual(run.snapshot()["active"]["Morgan"]["ends_at"] - run.now, 15 * MINUTE)
                run.advance(RIGHTING_TIME)
                self.assertFalse(ecostate(run)["tipped"])

    def test_unseen_righting_and_retip_do_not_create_new_firsthand_evidence(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        run = Simulation(camp(cook, worker("Morgan"), worker("Jordan")))
        start_cooking(run)
        run.advance(45 * MINUTE)
        first = evidence(run, "Morgan")
        self.assertEqual(len(notices(run, "Morgan")), 1)
        self.assertTrue(run.submit("Morgan", Request("move", "kitchen")))
        self.assertTrue(run.submit("Jordan", RIGHT))
        run.advance(RETIP - run.now)
        self.assertEqual(ecostate(run)["container_revision"], 3)
        self.assertTrue(run.submit("Morgan", Request("move", YARD)))
        run.advance(10 * MINUTE)
        self.assertEqual(evidence(run, "Morgan"), first)
        self.assertEqual(memory(run, "Morgan")["checked"],
                         {"condition": "tipped container", "checked_at": RETIP + 10 * MINUTE})

    def test_autonomous_cleanup_and_new_tip_depend_on_legitimate_discovery(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        for lamp in (0, 2):
            with self.subTest(lamp=lamp):
                run = Simulation(camp(cook, worker("Morgan", eager=True), lamp=lamp), seed=42)
                start_cooking(run)
                run.advance(RETIP)
                self.assertEqual(len(events(run, "right_bin", "completed")), int(lamp > 0))
                self.assertEqual(len(events(run, "disturbance", "occurred")), 2 if lamp else 1)
                self.assertEqual(ecostate(run)["container_revision"], 3 if lamp else 1)
                self.assertTrue(ecostate(run)["tipped"])
                self.assertEqual(ecostate(run)["scraps"], 0)
                self.assertEqual(run.snapshot()["servings"], 6)

    def test_same_time_forage_and_righting_follow_fifo(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        for cleanup_first in (True, False):
            with self.subTest(cleanup_first=cleanup_first):
                run = Simulation(camp(cook, worker("Morgan")))
                start_cooking(run)
                run.advance(RETIP - RIGHTING_TIME)
                self.assertTrue(run.submit("Morgan", RIGHT))
                if not cleanup_first:
                    run.advance(RIGHTING_TIME - MINUTE)
                    # Reissue the valid wake ticket after the animal arrival was queued.
                    run._schedule("Morgan", RETIP)
                run.advance(RETIP - run.now)
                self.assertEqual(ecostate(run)["tipped"], cleanup_first)
                self.assertEqual(ecostate(run)["container_revision"], 3 if cleanup_first else 2)
                self.assertEqual(ecostate(run)["scraps"], 0)
                self.assertEqual(len(events(run, "right_bin", "completed")), 1)

    def test_report_of_inspection_causes_visit_and_requires_current_observation(self):
        cook = person("Cook", "kitchen", skills=("cook",))
        for righted in (False, True):
            with self.subTest(righted=righted):
                run = Simulation(camp(cook, person("Witness", YARD), worker("Morgan", "commons", eager=True),
                                      worker("Jordan"), testimony=True, curiosity=(("Morgan", 20),)))
                start_cooking(run)
                run.advance(TIP - INSPECTION_TIME)
                self.assertTrue(run.submit("Witness", Request("inspect")))
                run.advance(INSPECTION_TIME)
                finding, = [item for item in run.snapshot()["perception"]["Witness"]["memory"]
                            if item["evidence"]["modality"] == "inspection"]
                reference = finding["reference"]
                if righted:
                    self.assertTrue(run.submit("Jordan", RIGHT))
                self.assertTrue(run.submit("Witness", Request("move", "commons")))
                run.advance(20 * MINUTE)
                self.assertTrue(run.propose_social("Witness", Exchange("Morgan", "testimony", reference=reference)))
                run.advance(DURATION)
                account = run.snapshot()["testimony"]["Morgan"]["accounts"][("Witness", reference)]
                data = account["delivery"]["testimony"]["observation"]["evidence"]
                self.assertEqual((data["detail"], data["at"]), ("tipped container", TIP))
                self.assertEqual(account["delivery"]["speaker"], "Witness")
                self.assertEqual(evidence(run, "Morgan"), [])
                self.assertIsNone(memory(run, "Morgan")["checked"])
                self.assertIsNotNone(memory(run, "Morgan")["visit"])
                run.advance(10 * MINUTE)
                self.assertEqual(memory(run, "Morgan")["checked"]["condition"],
                                 "upright container" if righted else "tipped container")
                self.assertEqual(any(e.staff == "Morgan" for e in events(run, "right_bin", "started")),
                                 not righted)
                if righted:
                    self.assertEqual(len(events(run, "maintenance visit", "abandoned")), 1)
                    updated = run.snapshot()["testimony"]["Morgan"]["accounts"][("Witness", reference)]
                    self.assertEqual(updated["compared"], "locally different")
                    self.assertEqual(updated["delivery"], account["delivery"])

    def test_wet_route_durations_fifo_and_fixed_arrivals(self):
        for weather_first in (False, True):
            with self.subTest(weather_first=weather_first):
                origin, destination = ("commons", YARD) if not weather_first else (YARD, "commons")
                run = Simulation(camp(person("Traveller", origin), raining=True), seed=4)
                # Only this boundary test controls when the traveller departs.
                run._wakes.clear()
                departure = 6 * HOUR
                def start():
                    self.assertTrue(run.submit("Traveller", Request("move", destination)))
                if weather_first:
                    run.advance(3 * HOUR)
                run._clock.schedule(departure, start)
                run.advance(departure - run.now)
                duration = (15 if weather_first else 10) * MINUTE
                self.assertEqual(ecostate(run)["wetness"][YARD], 4)
                self.assertEqual(run.snapshot()["active"]["Traveller"]["ends_at"], departure + duration)
                self.assertIsNone(memory(run, "Traveller")["crossing"])
                run.advance(duration - 1)
                self.assertEqual(run.snapshot()["locations"]["Traveller"], origin)
                run.advance(1)
                self.assertEqual(memory(run, "Traveller")["crossing"],
                                 {"origin": origin, "destination": destination,
                                  "elapsed": duration, "arrived_at": departure + duration})

        # Wetness falls below the threshold during this already-slow crossing.
        run = Simulation(camp(person("Traveller", "commons"), raining=True), seed=4)
        run._wakes.clear()
        run.advance(12 * HOUR - 5 * MINUTE)
        self.assertEqual(ecostate(run)["wetness"][YARD], 3)
        self.assertTrue(run.submit("Traveller", Request("move", YARD)))
        run.advance(5 * MINUTE)
        self.assertEqual(ecostate(run)["wetness"][YARD], 2)
        self.assertEqual(run.snapshot()["active"]["Traveller"]["ends_at"], 12 * HOUR + 10 * MINUTE)

    def test_same_uninformed_route_choice_has_different_physical_durations(self):
        for raining in (False, True):
            with self.subTest(raining=raining):
                run = Simulation(camp(person("Traveller", "commons"), raining=raining), seed=4)
                time = 6 * HOUR + 1
                run._schedule("Traveller", time)
                run.advance(time)
                move, = events(run, "move", "started")
                self.assertIn("to=service yard goal=meal", move.detail)
                duration = (15 if raining else 10) * MINUTE
                self.assertEqual(run.snapshot()["active"]["Traveller"]["ends_at"] - time, duration)
                self.assertIsNone(memory(run, "Traveller")["crossing"])

    def test_reference_replay_and_conservation(self):
        scenario = maintenance_camp()
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                run = Simulation(scenario, seed=seed)
                stepped = Simulation(scenario, seed=seed)
                run.advance(4 * DAY)
                while stepped.now < stepped.horizon:
                    stepped.advance(2137)
                self.assertEqual(run.history, stepped.history)
                self.assertEqual(run.snapshot(), stepped.snapshot())
                state = run.snapshot()
                for person in scenario.staff:
                    completed = {e.action for e in run.history if e.phase == "completed"
                                 and e.staff == person.name}
                    self.assertTrue({"meal", "leisure", "sleep"} <= completed)
                self.assertTrue(events(run, "prepare", "completed"))
                self.assertTrue(events(run, "social", "completed"))
                trips = events(run, "wildlife travel", "completed")
                self.assertTrue(trips)
                batches = [job for job in scenario.camp.jobs if state["job_states"][job.target] == "cooked"]
                self.assertTrue(batches)
                self.assertEqual(state["ingredients"],
                                 scenario.camp.ingredients - sum(job.ingredients for job in batches))
                self.assertEqual(state["servings"], scenario.servings + sum(job.produces for job in batches)
                                 - len(events(run, "meal", "started")))
                self.assertGreaterEqual(state["ingredients"], state["reserved_ingredients"])
                self.assertGreaterEqual(state["servings"], 0)
                self.assertIn(state["ecology"]["scraps"], range(7))
                tips = sum("refuse container" in e.detail for e in events(run, "disturbance", "occurred"))
                cleanups = len(events(run, "right_bin", "completed"))
                self.assertEqual(state["ecology"]["container_revision"], tips + cleanups)
                self.assertEqual(tips - cleanups, int(state["ecology"]["tipped"]))

    def test_seven_day_horizon_and_normal_playback(self):
        run = Simulation(maintenance_camp(days=7))
        self.assertEqual(Playback(run.advance).update(60), 16 * 60)
        run.advance(8 * DAY)
        self.assertEqual(run.now, 7 * DAY)

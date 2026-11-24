"""Private sensory testimony, one-hop attribution, and ordinary investigation."""

from dataclasses import replace
import unittest

from summer_camp.clock import DAY, Playback
from summer_camp.cognition import Staff, StaffProfile
from summer_camp.perception import HOUR, MEMORY_SIZE, MINUTE, Environment, Fitting, Link
from summer_camp.reference_camp import perception_camp, witness_camp
from summer_camp.simulation import CampLayout, Scenario, Simulation
from summer_camp.social import COOLDOWN, DURATION, Exchange, SocialProfile
from summer_camp.world import Request

PATHS = perception_camp().camp.paths
FITTING = Fitting("private source key", "shutter", "boathouse")
ACOUSTIC = (Link("commons", "shore path", 2), Link("shore path", "boathouse", 2))


def person(name, location="commons", leisure=0):
    return Staff(name, location, (0, 0, 0, leisure), (0, 0, 0, 0), StaffProfile("test"))


def fixture(*roster, curiosity=(), acoustic=ACOUSTIC, talkers=()):
    social = tuple((staff.name, SocialProfile(1 if staff.name in talkers else -1)) for staff in roster)
    return Scenario(roster, 1, 20, camp=CampLayout(PATHS, (), 0), social=social,
                    environment=Environment((FITTING,), acoustic=acoustic, curiosity=curiosity),
                    witness_reports=True)


def accounts(run, staff):
    return run.snapshot()["testimony"][staff]["accounts"]


def report(peer, reference=1):
    return Exchange(peer, "testimony", reference=reference)


def relay(peer, witness="Avery", reference=1):
    return Exchange(peer, "relay", witness=witness, reference=reference)


def events(run, action, phase):
    return [event for event in run.history if (event.action, event.phase) == (action, phase)]


class TestimonyTests(unittest.TestCase):
    def test_autonomous_report_changes_decision_without_transferring_firsthand_knowledge(self):
        roster = (person("Avery", leisure=40), person("Morgan", "kitchen", leisure=25),
                  person("Casey", "cabins"))
        receptive = fixture(*roster, curiosity=(("Morgan", 35),), talkers=("Avery",))
        indifferent = replace(receptive, environment=replace(receptive.environment, curiosity=()))
        control = replace(receptive, witness_reports=False)
        runs = [Simulation(case, seed=42) for case in (receptive, indifferent, control)]
        for run in runs:
            run.queue_disturbance(10 * MINUTE, FITTING.key, "gust")
            run.advance(2 * HOUR)
            self.assertEqual(run.snapshot()["fitting_positions"], {FITTING.key: True})
        active, uninterested, silent = runs
        delivery = accounts(active, "Morgan")[("Avery", 1)]["delivery"]
        self.assertEqual(delivery["speaker"], "Avery")
        cue = delivery["testimony"]["observation"]["evidence"]
        self.assertEqual(cue, {"at": 10 * MINUTE, "modality": "sound", "detail": "clatter",
                               "area": "shore path", "label": None})
        self.assertNotIn(FITTING.key, repr(delivery))
        self.assertNotIn("gust", repr(delivery))
        self.assertEqual(accounts(active, "Casey"), {})
        self.assertEqual(active.snapshot()["perception"]["Morgan"]["memory"], [])
        selected, = events(active, "investigation", "selected")
        self.assertEqual((selected.staff, selected.at), ("Morgan", 70 * MINUTE))
        self.assertIn("source=testimony", selected.detail)
        completed, = events(active, "inspect", "completed")
        self.assertEqual((completed.at, completed.detail), (85 * MINUTE, "inconclusive"))
        self.assertFalse(events(uninterested, "inspect", "started"))
        self.assertFalse(events(silent, "inspect", "started"))
        self.assertEqual(accounts(uninterested, "Morgan")[("Avery", 1)]["assessment"], "disregarded")

    def test_only_retained_witness_references_are_admitted_and_payload_survives_eviction(self):
        run = Simulation(fixture(person("Avery"), person("Morgan"), person("Jordan")))
        self.assertFalse(run.propose_social("Avery", report("Morgan")))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(0)
        self.assertFalse(run.propose_social("Avery", report("Morgan", 999)))
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        for second in range(1, MEMORY_SIZE + 2):
            run.queue_disturbance(second, FITTING.key, "gust")
        run.advance(DURATION - 1)
        self.assertEqual(accounts(run, "Morgan"), {})
        retained = run.snapshot()["perception"]["Avery"]["memory"]
        self.assertEqual([item["reference"] for item in retained], list(range(3, 11)))
        run.advance(1)
        delivery = accounts(run, "Morgan")[("Avery", 1)]["delivery"]
        self.assertEqual(delivery["testimony"]["observation"]["evidence"]["at"], 0)
        self.assertFalse(run.propose_social("Avery", report("Jordan")))
        self.assertTrue(run.propose_social("Avery", report("Jordan", 3)))
        run.advance(DURATION)
        self.assertIn(("Avery", 3), accounts(run, "Jordan"))

    def test_cancelled_report_retries_with_one_delivery_and_no_reservations(self):
        run = Simulation(fixture(person("Avery"), person("Morgan")))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(0)
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        run.advance(MINUTE)
        self.assertTrue(run.disengage("Morgan"))
        self.assertFalse(run.propose_social("Avery", report("Morgan")))
        run.advance(COOLDOWN - MINUTE)
        self.assertEqual(accounts(run, "Morgan"), {})
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        key, = run.snapshot()["encounters"]
        run._clock.schedule(run.now + DURATION, lambda: run._close_encounter(key))
        run.advance(DURATION)
        claim, = accounts(run, "Morgan").values()
        self.assertEqual(claim["delivery"]["first_report_at"], COOLDOWN + DURATION)
        self.assertEqual(len(events(run, "social", "completed")), 1)
        self.assertEqual(run.snapshot()["encounters"], {})
        self.assertTrue(all(action["request"]["kind"] != "social"
                            for action in run.snapshot()["active"].values()))

    def test_one_hop_and_duplicate_delivery_across_multiple_intermediaries(self):
        roster = tuple(person(name) for name in ("Avery", "Morgan", "Jordan", "Cameron", "Taylor"))
        run = Simulation(fixture(*roster))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(0)
        for peer in ("Morgan", "Cameron"):
            self.assertTrue(run.propose_social("Avery", report(peer)))
            run.advance(DURATION)
        self.assertTrue(run.propose_social("Morgan", relay("Jordan")))
        run.advance(DURATION)
        original = accounts(run, "Jordan")
        delivery = original[("Avery", 1)]["delivery"]
        self.assertEqual((delivery["speaker"], delivery["relayed"]), ("Morgan", True))
        self.assertEqual(delivery["first_report_at"], DURATION)
        self.assertEqual(delivery["delivered_at"], 3 * DURATION)
        self.assertEqual(delivery["testimony"], accounts(run, "Morgan")[("Avery", 1)]["delivery"]["testimony"])
        self.assertFalse(run.propose_social("Jordan", relay("Taylor")))
        self.assertTrue(run.propose_social("Cameron", relay("Jordan")))
        run.advance(DURATION)
        self.assertEqual(accounts(run, "Jordan"), original)
        self.assertIn("delivery=duplicate", events(run, "social", "completed")[-1].detail)
        self.assertEqual(accounts(run, "Taylor"), {})

    def test_distinct_witness_accounts_with_conflicting_directions_are_retained(self):
        acoustic = (*ACOUSTIC, Link("boathouse", "woodland", 2), Link("woodland", "workshop", 2))
        run = Simulation(fixture(person("Avery"), person("Cameron", "workshop"), person("Morgan"),
                                 acoustic=acoustic))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(0)
        self.assertTrue(run.submit("Cameron", Request("move", "commons")))
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Cameron", report("Morgan")))
        run.advance(DURATION)
        retained = accounts(run, "Morgan")
        self.assertEqual(set(retained), {("Avery", 1), ("Cameron", 1)})
        directions = {account["delivery"]["testimony"]["observation"]["evidence"]["area"]
                      for account in retained.values()}
        self.assertEqual(directions, {"shore path", "woodland"})
        self.assertTrue(all(account["compared"] is None for account in retained.values()))

    def test_indistinct_testimony_does_not_invent_investigation_destination(self):
        acoustic = (Link("boathouse", "commons", 6),)
        run = Simulation(fixture(person("Avery"), person("Morgan"), acoustic=acoustic,
                                 curiosity=(("Morgan", 80),)))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(0)
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        run.advance(HOUR)
        account = accounts(run, "Morgan")[("Avery", 1)]
        self.assertIsNone(account["delivery"]["testimony"]["observation"]["evidence"]["area"])
        self.assertIsNone(run.snapshot()["testimony"]["Morgan"]["pending"])
        self.assertFalse(events(run, "inspect", "started"))

    def test_duplicate_after_expiry_cannot_reopen_investigation(self):
        # Morgan starts beyond hearing and later joins the other two.
        run = Simulation(fixture(person("Avery"), person("Jordan"), person("Morgan", "kitchen"),
                                 curiosity=(("Morgan", 35),)))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(0)
        self.assertTrue(run.submit("Morgan", Request("move", "commons")))
        self.assertTrue(run.propose_social("Avery", report("Jordan")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        run.advance(30 * MINUTE)
        self.assertEqual(len(events(run, "inspect", "completed")), 1)
        run.advance(50 * MINUTE)
        # Return from the inconclusive shore inspection for a relay of the same root.
        self.assertTrue(run.submit("Morgan", Request("move", "commons")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Jordan", relay("Morgan")))
        run.advance(DURATION)
        self.assertEqual(len(events(run, "inspect", "completed")), 1)
        self.assertIsNone(run.snapshot()["testimony"]["Morgan"]["pending"])
        self.assertIn("delivery=duplicate", events(run, "social", "completed")[-1].detail)

    def test_late_report_can_be_remembered_without_restarting_the_investigation_window(self):
        run = Simulation(fixture(person("Avery"), person("Morgan", "kitchen"),
                                 curiosity=(("Morgan", 35),)))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.advance(90 * MINUTE)
        self.assertTrue(run.submit("Morgan", Request("move", "commons")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Avery", report("Morgan")))
        run.advance(DURATION)
        self.assertIn(("Avery", 1), accounts(run, "Morgan"))
        self.assertIsNone(run.snapshot()["testimony"]["Morgan"]["pending"])
        self.assertFalse(events(run, "investigation", "selected"))

    def test_topic_rule_distinguishes_observations_for_same_peer(self):
        run = Simulation(fixture(person("Avery"), person("Morgan")))
        run.queue_disturbance(0, FITTING.key, "gust")
        run.queue_disturbance(MINUTE, FITTING.key, "gust")
        run.advance(MINUTE)
        self.assertTrue(run.propose_social("Avery", report("Morgan", 1)))
        run.advance(COOLDOWN)
        self.assertFalse(run.propose_social("Avery", report("Morgan", 1)))
        self.assertTrue(run.propose_social("Avery", report("Morgan", 2)))
        run.advance(DURATION)
        self.assertEqual(set(accounts(run, "Morgan")), {("Avery", 1), ("Avery", 2)})

    def test_four_day_reference_runs_preserve_replay_and_ordinary_life(self):
        camp = witness_camp()
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                whole = Simulation(camp, seed=seed)
                stepped = Simulation(camp, seed=seed)
                whole.advance(4 * DAY)
                while stepped.now < stepped.horizon:
                    stepped.advance(2137)
                self.assertEqual(whole.history, stepped.history)
                self.assertEqual(whole.snapshot(), stepped.snapshot())
                self.assertEqual(len(events(whole, "disturbance", "occurred")), 4)
                self.assertTrue(events(whole, "inspect", "completed"))
                conversations = [event.detail for event in events(whole, "social", "completed")]
                for kind in ("testimony", "relay"):
                    self.assertTrue(any(f"kind={kind} " in detail and "delivery=received" in detail
                                        for detail in conversations))
                for staff in camp.staff:
                    completed = [e.action for e in whole.history if e.staff == staff.name
                                 and e.phase == "completed"]
                    self.assertIn(completed.count("meal"), range(8, 17))
                    self.assertIn(completed.count("sleep"), range(3, 5))
                    self.assertIn("leisure", completed)
                state = whole.snapshot()
                self.assertIn("ready", state["job_states"].values())
                self.assertIn("repaired", state["job_states"].values())
                batches = [job for job in camp.camp.jobs if state["job_states"][job.target] == "cooked"]
                self.assertTrue(batches)
                self.assertEqual(state["ingredients"], camp.camp.ingredients - sum(j.ingredients for j in batches))
                self.assertEqual(state["servings"], camp.servings + sum(j.produces for j in batches)
                                 - len(events(whole, "meal", "started")))
                self.assertGreaterEqual(state["ingredients"], state["reserved_ingredients"])
                self.assertGreaterEqual(state["servings"], 0)

    def test_seven_days_and_normal_playback(self):
        run = Simulation(witness_camp(days=7))
        self.assertEqual(Playback(run.advance).update(60), 16 * 60)
        run.advance(8 * DAY)
        self.assertEqual(run.now, 7 * DAY)

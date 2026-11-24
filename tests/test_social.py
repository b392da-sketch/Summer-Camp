"""Encounter mechanics, private claims, and voluntary cooperation."""

from dataclasses import replace
import unittest

from summer_camp.clock import DAY
from summer_camp.cognition import HOUR, Staff, StaffProfile
from summer_camp.reference_camp import PATHS, social_camp
from summer_camp.simulation import CampLayout, Scenario, Simulation
from summer_camp.social import COOLDOWN, DURATION, Exchange, SocialProfile
from summer_camp.world import MINUTE, Job, Request


RACK = Job("rack", "repair", "boathouse", 30 * MINUTE, "repair")


def staff(name, location="commons", *, repair=False, needs=(0, 0, 0, 40)):
    return Staff(name, location, needs, (0, 0, -100, 0),
                 StaffProfile("test", capabilities=("repair",) if repair else ()))


def fixture(*roster, profiles=None, jobs=(), servings=0):
    profiles = profiles or tuple((person.name, SocialProfile(-1)) for person in roster)
    return Scenario(roster, 1, servings, camp=CampLayout(PATHS, jobs, 0), social=profiles)


def events(run, action, phase):
    return [event for event in run.history if (event.action, event.phase) == (action, phase)]


class SocialTests(unittest.TestCase):
    def test_only_co_present_available_staff_can_converse(self):
        alex, bo = staff("Alex"), staff("Bo")
        cases = (
            (staff("Bo", "cabins"), None),
            (bo, Request("move", "cabins")),
            (staff("Bo", "cabins"), Request("sleep")),
            (staff("Bo", "boathouse", repair=True), Request("prepare", target="rack")),
            (staff("Bo", "kitchen"), Request("meal")),
        )
        for person, action in cases:
            with self.subTest(action=action):
                # For stationary actions put Alex at the same facility.
                origin = person.location if action and action.kind != "move" else "commons"
                run = Simulation(fixture(replace(alex, location=origin), person, jobs=(RACK,), servings=1))
                if action:
                    self.assertTrue(run.submit("Bo", action))
                self.assertFalse(run.propose_social("Alex", Exchange("Bo")))
                self.assertEqual(run.snapshot()["encounters"], {})

        run = Simulation(fixture(alex, bo))
        self.assertTrue(run.submit("Bo", Request("leisure")))
        self.assertTrue(run.propose_social("Alex", Exchange("Bo")))
        run.advance(DURATION)
        self.assertEqual(run.snapshot()["active"]["Bo"]["request"]["kind"], "leisure")
        run.advance(55 * MINUTE)
        self.assertEqual(len(events(run, "leisure", "completed")), 2)

    def test_refusal_and_co_presence_do_not_change_relationships(self):
        roster = (staff("Alex"), staff("Bo"))
        profiles = (("Alex", SocialProfile(-1)), ("Bo", SocialProfile(-4)))
        run = Simulation(fixture(*roster, profiles=profiles))
        self.assertFalse(run.propose_social("Alex", Exchange("Bo")))
        run.advance(DURATION)
        self.assertEqual(len(events(run, "social", "refused")), 1)
        self.assertEqual(run.snapshot()["encounters"], {})
        self.assertEqual([value["relationships"] for value in run.snapshot()["social"].values()], [{}, {}])

    def test_simultaneous_proposals_and_cancelled_callback_cannot_overlap(self):
        run = Simulation(fixture(staff("Alex"), staff("Bo"), staff("Casey")))
        self.assertTrue(run.propose_social("Alex", Exchange("Bo")))
        self.assertFalse(run.propose_social("Casey", Exchange("Bo")))
        self.assertEqual(len(run.snapshot()["encounters"]), 1)
        run.advance(MINUTE)
        self.assertTrue(run.disengage("Bo"))
        self.assertFalse(run.disengage("Alex"))
        self.assertTrue(run.propose_social("Casey", Exchange("Bo")))
        run.advance(DURATION - MINUTE)
        self.assertEqual(len(events(run, "social", "completed")), 0)
        self.assertEqual(len(run.snapshot()["encounters"]), 1)
        run.advance(MINUTE)
        self.assertEqual([event.staff for event in events(run, "social", "completed")], ["Casey"])
        self.assertEqual(run.snapshot()["encounters"], {})
        run.advance(DURATION)
        self.assertEqual(len(events(run, "social", "cancelled")), 1)
        self.assertEqual(len(events(run, "social", "completed")), 1)

    def test_encounter_at_horizon_completes_once_and_late_start_fails(self):
        quiet = (staff("Alex", needs=(0, 0, 0, 0)), staff("Bo", needs=(0, 0, 0, 0)))
        run = Simulation(fixture(*quiet))
        run.horizon = 2 * DURATION
        run.advance(DURATION)
        self.assertTrue(run.propose_social("Bo", Exchange("Alex")))
        key, = run.snapshot()["encounters"]
        # A duplicate callback for the same reservation cannot resolve it again.
        run._clock.schedule(run.horizon, lambda: run._close_encounter(key))
        run.advance(DURATION)
        self.assertEqual(len(events(run, "social", "completed")), 1)
        self.assertEqual(run.snapshot()["encounters"], {})
        self.assertEqual(run.snapshot()["active"], {})
        self.assertFalse(run.propose_social("Alex", Exchange("Bo")))
        too_late = Simulation(fixture(*quiet))
        too_late.horizon = 2 * DURATION
        too_late.advance(DURATION + 1)
        self.assertFalse(too_late.propose_social("Alex", Exchange("Bo")))
        self.assertEqual(too_late.snapshot()["encounters"], {})

    def test_directed_affinity_changes_differently_after_same_greeting(self):
        profiles = (("Alex", SocialProfile(1)), ("Bo", SocialProfile(-1)))
        run = Simulation(fixture(staff("Alex"), staff("Bo"), profiles=profiles))
        self.assertTrue(run.propose_social("Alex", Exchange("Bo")))
        run.advance(DURATION)
        links = run.snapshot()["social"]
        self.assertEqual(links["Alex"]["relationships"]["Bo"], {"affinity": 1, "familiarity": 1, "trust": 0})
        self.assertEqual(links["Bo"]["relationships"]["Alex"], {"affinity": 0, "familiarity": 1, "trust": 0})
        run.advance(60 * MINUTE)
        self.assertEqual(len(events(run, "social", "completed")), 1)

    def test_spoken_stale_claim_is_attributed_and_contradicted_only_on_inspection(self):
        roster = (staff("Alex", "boathouse", needs=(0, 0, 0, 0)),
                  staff("Bo"), staff("Casey", "boathouse", repair=True, needs=(0, 0, 0, 0)))
        rack = replace(RACK, duration=5 * MINUTE)
        run = Simulation(fixture(*roster, jobs=(rack,)))
        report = Exchange("Bo", "report", "boathouse", "rack")
        self.assertFalse(run.propose_social("Alex", report))
        run.advance(0)
        self.assertTrue(run.submit("Alex", Request("move", "commons")))
        self.assertTrue(run.submit("Casey", Request("prepare", target="rack")))
        run.advance(10 * MINUTE)
        self.assertEqual(run.snapshot()["job_states"]["rack"], "repaired")
        self.assertTrue(run.propose_social("Alex", report))
        run.advance(DURATION - 1)
        self.assertFalse(run.snapshot()["social"]["Bo"]["claims"])
        run.advance(1)
        state = run.snapshot()
        self.assertEqual(state["social"]["Bo"]["claims"], [
            {"speaker": "Alex", "location": "boathouse", "target": "rack", "value": "pending",
             "observed_at": 0, "delivered_at": 15 * MINUTE},
        ])
        self.assertFalse(state["social"]["Casey"]["claims"])
        self.assertNotIn("prepare:boathouse", state["minds"]["Bo"]["memory"])
        # The encounter temporarily paused Bo's leisure. Move after it completes.
        run.advance(50 * MINUTE)
        self.assertTrue(run.submit("Bo", Request("move", "boathouse")))
        run.advance(10 * MINUTE)
        self.assertEqual(run.snapshot()["social"]["Bo"]["assessed"], {0: "contradicted"})

    def test_cancelled_report_delivers_no_claim_and_restores_leisure(self):
        roster = (staff("Alex", "boathouse", needs=(0, 0, 0, 0)), staff("Bo"))
        run = Simulation(fixture(*roster, jobs=(RACK,)))
        run.advance(0)
        self.assertTrue(run.submit("Alex", Request("move", "commons")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Alex", Exchange("Bo", "report", "boathouse", "rack")))
        run.advance(MINUTE)
        self.assertTrue(run.disengage("Bo"))
        self.assertEqual(run.snapshot()["active"]["Bo"]["ends_at"], 56 * MINUTE)
        run.advance(DURATION)
        self.assertEqual(run.snapshot()["social"]["Bo"]["claims"], [])
        self.assertEqual(run.snapshot()["social"]["Bo"]["relationships"], {})
        self.assertEqual(events(run, "social", "completed"), [])

    def test_accepted_help_becomes_obsolete_after_inspection(self):
        roster = (staff("Alex", "boathouse", needs=(0, 0, 0, 0)),
                  staff("Bo", repair=True, needs=(0, 0, 0, 0)),
                  staff("Casey", "boathouse", repair=True, needs=(0, 0, 0, 0)))
        run = Simulation(fixture(*roster, jobs=(replace(RACK, duration=5 * MINUTE),)))
        run.advance(0)
        self.assertTrue(run.submit("Alex", Request("move", "commons")))
        self.assertTrue(run.submit("Casey", Request("prepare", target="rack")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Alex", Exchange("Bo", "help", "boathouse", "rack")))
        run.advance(DURATION)
        self.assertEqual(run.snapshot()["social"]["Bo"]["help"][0]["state"], "accepted")
        run.advance(10 * MINUTE)
        state = run.snapshot()
        self.assertEqual(state["social"]["Bo"]["help"][0]["state"], "obsolete")
        self.assertEqual(state["social"]["Alex"]["responses"][0][2], "accepted")
        self.assertEqual([event.staff for event in events(run, "prepare", "completed")], ["Casey"])

    def test_ask_reports_only_one_personally_observed_fact(self):
        roster = (staff("Alex", needs=(0, 0, 0, 0)),
                  staff("Bo", "boathouse", needs=(0, 0, 0, 0)))
        for target in ("rack", "unknown"):
            with self.subTest(target=target):
                run = Simulation(fixture(*roster, jobs=(RACK, replace(RACK, target="other"))))
                run.advance(0)
                self.assertTrue(run.submit("Bo", Request("move", "commons")))
                run.advance(10 * MINUTE)
                self.assertTrue(run.propose_social("Alex", Exchange("Bo", "ask", "boathouse", target)))
                run.advance(DURATION)
                claims = run.snapshot()["social"]["Alex"]["claims"]
                self.assertEqual([claim["target"] for claim in claims], ["rack"] if target == "rack" else [])
                if claims:
                    self.assertEqual(claims[0]["speaker"], "Bo")

    def test_help_can_be_declined_after_agreeing_to_a_conversation(self):
        roster = (staff("Alex", "boathouse", needs=(0, 0, 0, 0)),
                  staff("Bo", "boathouse", repair=True, needs=(0, 0, 0, 0)))
        profiles = (("Alex", SocialProfile(-1)), ("Bo", SocialProfile(-1, -1)))
        run = Simulation(fixture(*roster, profiles=profiles, jobs=(RACK,)))
        run.advance(0)
        self.assertTrue(run.propose_social("Alex", Exchange("Bo", "help", "boathouse", "rack")))
        run.advance(DURATION)
        state = run.snapshot()
        self.assertEqual(state["social"]["Bo"]["help"][0]["state"], "declined")
        self.assertEqual(state["social"]["Alex"]["responses"][0][2], "declined")
        self.assertEqual(state["social"]["Alex"]["relationships"]["Bo"]["affinity"], -1)
        self.assertEqual(state["social"]["Bo"]["relationships"]["Alex"]["affinity"], 0)
        self.assertEqual(state["job_states"]["rack"], "pending")

    def test_help_is_deferred_while_another_accepted_request_is_pending(self):
        alex = staff("Alex", "boathouse", needs=(0, 0, 0, 0))
        bo = staff("Bo", repair=True)
        casey = replace(alex, name="Casey")
        run = Simulation(fixture(alex, bo, casey, jobs=(RACK, replace(RACK, target="hook"))))
        run.advance(0)
        for name in ("Alex", "Casey"):
            self.assertTrue(run.submit(name, Request("move", "commons")))
        run.advance(10 * MINUTE)
        self.assertTrue(run.propose_social("Alex", Exchange("Bo", "help", "boathouse", "rack")))
        run.advance(DURATION)
        self.assertTrue(run.propose_social("Casey", Exchange("Bo", "help", "boathouse", "hook")))
        run.advance(DURATION)
        responses = run.snapshot()["social"]["Bo"]["help"]
        self.assertEqual([help_request["state"] for help_request in responses], ["accepted", "deferred"])

    def test_accepted_help_expires_when_equipment_remains_busy(self):
        alex = staff("Alex", "boathouse", needs=(0, 0, 0, 0))
        bo = staff("Bo", "boathouse", repair=True, needs=(0, 0, 0, 0))
        casey = replace(bo, name="Casey")
        run = Simulation(fixture(alex, bo, casey, jobs=(replace(RACK, duration=6 * HOUR),)))
        self.assertTrue(run.submit("Casey", Request("prepare", target="rack")))
        run.advance(0)
        self.assertTrue(run.propose_social("Alex", Exchange("Bo", "help", "boathouse", "rack")))
        run.advance(DURATION)
        self.assertEqual(run.snapshot()["social"]["Bo"]["help"][0]["state"], "accepted")
        run.advance(5 * HOUR)
        state = run.snapshot()
        self.assertEqual(state["social"]["Bo"]["help"][0]["state"], "expired")
        self.assertEqual(state["social"]["Alex"]["responses"][0][2], "accepted")
        self.assertEqual(state["job_states"]["rack"], "pending")
        self.assertEqual([event.staff for event in events(run, "prepare", "started")], ["Casey"])

    def test_autonomous_conversation_changes_work_and_leaves_third_party_uninformed(self):
        roster = (staff("Alex", "boathouse"), staff("Bo", repair=True),
                  staff("Casey", "cabins", needs=(0, 95, 0, 0)))
        profiles = (("Alex", SocialProfile(1)), ("Bo", SocialProfile(-1)), ("Casey", SocialProfile(-4)))
        scenario = fixture(*roster, profiles=profiles, jobs=(RACK,))
        social = Simulation(scenario)
        control = Simulation(replace(scenario, social=()))
        for run in (social, control):
            run.advance(2 * HOUR)
        state = social.snapshot()
        self.assertEqual(control.snapshot()["job_states"]["rack"], "pending")
        self.assertEqual(state["job_states"]["rack"], "repaired")
        self.assertEqual(state["social"]["Bo"]["help"][0]["state"], "fulfilled")
        self.assertEqual(state["social"]["Bo"]["assessed"], {0: "confirmed"})
        self.assertEqual(state["social"]["Bo"]["relationships"]["Alex"]["trust"], 1)
        self.assertEqual(state["social"]["Alex"]["relationships"]["Bo"]["trust"], 0)
        self.assertEqual(state["social"]["Alex"]["responses"][0][2], "accepted")
        self.assertFalse(state["social"]["Casey"]["claims"])
        self.assertNotIn("prepare:boathouse", state["minds"]["Casey"]["memory"])
        self.assertFalse(state["minds"]["Alex"]["memory"]["prepare:boathouse"]["jobs"][0]["done"])
        self.assertTrue(state["minds"]["Bo"]["memory"]["prepare:boathouse"]["jobs"][0]["done"])
        completed = events(social, "social", "completed")[0]
        self.assertEqual(completed.staff, "Alex")
        self.assertIn("kind=help", completed.detail)
        self.assertLess(completed.at, events(social, "prepare", "started")[0].at)
        self.assertEqual([event.staff for event in events(social, "prepare", "completed")], ["Bo"])

    def test_reference_runs_are_autonomous_deterministic_and_conserve_food(self):
        scenario = social_camp()
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                whole = Simulation(scenario, seed=seed)
                stepped = Simulation(scenario, seed=seed)
                whole.advance(4 * DAY)
                while stepped.now < stepped.horizon:
                    stepped.advance(2137)
                self.assertEqual(whole.history, stepped.history)
                self.assertEqual(whole.snapshot(), stepped.snapshot())
                state = whole.snapshot()
                self.assertEqual(state["encounters"], {})
                self.assertTrue(all(action["request"]["kind"] != "social"
                                    for action in state["active"].values()))
                conversations = events(whole, "social", "completed")
                self.assertGreater(len(conversations), 0)
                self.assertLess(len(conversations), 150)
                pair_last = {}
                for conversation in conversations:
                    peer = conversation.detail.split()[0].removeprefix("peer=")
                    pair = tuple(sorted((conversation.staff, peer)))
                    self.assertGreaterEqual(conversation.at - pair_last.get(pair, -COOLDOWN), COOLDOWN)
                    pair_last[pair] = conversation.at
                for person in scenario.staff:
                    performed = [event.action for event in whole.history
                                 if event.staff == person.name and event.phase == "completed"]
                    self.assertIn(performed.count("meal"), range(8, 17))
                    self.assertIn(performed.count("sleep"), range(3, 5))
                    self.assertIn("leisure", performed)
                jobs = events(whole, "prepare", "completed")
                self.assertEqual(len(jobs), len({event.detail for event in jobs}))
                self.assertIn("ready", state["job_states"].values())
                self.assertIn("repaired", state["job_states"].values())
                cooked = [job for job in scenario.camp.jobs if state["job_states"][job.target] == "cooked"]
                self.assertTrue(cooked)
                self.assertEqual(state["ingredients"], scenario.camp.ingredients - sum(j.ingredients for j in cooked))
                self.assertEqual(state["servings"], scenario.servings + sum(j.produces for j in cooked)
                                 - len(events(whole, "meal", "started")))
                self.assertGreaterEqual(state["ingredients"], state["reserved_ingredients"])
        seven = Simulation(social_camp(days=7))
        self.assertEqual(seven.advance(8 * DAY), 7 * DAY)

from fractions import Fraction
import unittest

from summer_camp.clock import DAY, Clock, Playback
from summer_camp.cognition import Staff
from summer_camp.simulation import Event, Scenario, Simulation
from summer_camp.world import MINUTE, Request

NEUTRAL = (0, 0, 0, 0)


class TimeTests(unittest.TestCase):
    def test_playback_relationship_pause_and_rate(self):
        clock = Clock()
        playback = Playback(clock.advance)
        for hours, expected_days in ((6, 4), (Fraction(9, 2), 7)):
            playback.update(hours * 3600)
            self.assertEqual(clock.now, expected_days * DAY)
        playback.paused = True
        self.assertEqual(playback.update(100), 0)
        self.assertEqual(clock.now, 7 * DAY)
        playback.paused = False
        playback.rate = Fraction(3, 2)
        self.assertEqual(playback.update(Fraction(1, 3)), 0)
        self.assertEqual(playback.update(Fraction(1, 3)), 1)
        self.assertEqual(clock.now, 7 * DAY + 1)

    def test_playback_reports_applied_time_at_scenario_horizon(self):
        run = Simulation(Scenario(days=1))
        run.advance(DAY - 3)
        playback = Playback(run.advance)
        self.assertEqual(playback.update(1), 3)
        self.assertEqual(run.now, DAY)
        self.assertEqual(playback.update(1), 0)

    def test_scenario_limit_does_not_limit_clock(self):
        with self.assertRaises(ValueError):
            Scenario(days=8)
        run = Simulation()
        run.advance(8 * DAY)
        self.assertEqual(run.now, 7 * DAY)
        clock = Clock()
        clock.advance(8 * DAY)
        self.assertEqual(clock.now, 8 * DAY)

    def test_simultaneous_callbacks_are_fifo_including_new_callbacks(self):
        clock = Clock()
        observed = []

        def first():
            observed.append("first")
            clock.schedule(clock.now, lambda: observed.append("new"))

        clock.schedule(5, first)
        clock.schedule(5, lambda: observed.append("second"))
        clock.advance(5)
        self.assertEqual(observed, ["first", "second", "new"])


class SimulationTests(unittest.TestCase):
    def test_four_day_camp_runs_with_independent_staff_and_persistent_effects(self):
        run = Simulation(Scenario(days=4), seed=42)
        run.advance(4 * DAY)
        state = run.snapshot()
        self.assertEqual(run.now, 4 * DAY)
        completed = [event for event in run.history if event.phase == "completed"]
        activities = {"move", "meal", "work", "rest", "leisure"}
        for staff in ("Ada", "Ben", "Clara"):
            self.assertTrue(activities - {"work"} <= {
                event.action for event in completed if event.staff == staff
            })
        self.assertEqual({event.action for event in completed}, activities)
        self.assertTrue(all(event.action in activities for event in run.history))
        self.assertEqual(state["repair_states"], {
            "canoe rack": "repaired", "supply cart": "repaired", "trail sign": "repaired"
        })
        self.assertEqual(sum(event.action == "work" for event in completed), 3)
        meals_started = sum(event.action == "meal" and event.phase == "started" for event in run.history)
        self.assertGreater(meals_started, 0)
        self.assertEqual(state["servings"], 200 - meals_started)

    def test_work_interruption_resumes_only_remaining_duration(self):
        run = Simulation(seed=42)
        run.advance(219 * MINUTE)
        self.assertIn(Event(115 * MINUTE, "Clara", "interrupted", "work", "target=canoe rack, hunger, 2400s remaining"),
                      run.history)
        self.assertIn(Event(180 * MINUTE, "Clara", "resumed", "work", "target=canoe rack"), run.history)
        self.assertTrue(any(event.staff == "Clara" and event.action == "meal"
                            and event.phase == "completed" for event in run.history))
        self.assertEqual(run.snapshot()["repair_states"]["canoe rack"], "damaged")
        run.advance(MINUTE)
        self.assertIn(Event(220 * MINUTE, "Clara", "completed", "work", "target=canoe rack damaged -> repaired"),
                      run.history)
        self.assertEqual(run.snapshot()["repair_states"]["canoe rack"], "repaired")

    def test_interrupted_work_waits_if_another_staff_member_takes_bench(self):
        ada = Staff("Ada", "workshop", (67, 0, 95, 0), NEUTRAL)
        ben = Staff("Ben", "workshop", NEUTRAL, (-200, -200, -200, -200))
        run = Simulation(Scenario(staff=(ada, ben)))
        run.advance(80 * MINUTE)
        self.assertIn(Event(15 * MINUTE, "Ada", "interrupted", "work", "target=canoe rack, hunger, 5100s remaining"),
                      run.history)
        self.assertIn(Event(15 * MINUTE, "Ben", "started", "work", "target=canoe rack"), run.history)
        self.assertIn(Event(80 * MINUTE, "Ada", "redirected", "work", "resource occupied"), run.history)
        self.assertFalse(any(event.phase == "resumed" for event in run.history))
        self.assertEqual(run.snapshot()["minds"]["Ada"]["repair_commitment"],
                         {"target": "canoe rack", "remaining": 5100})

    def test_peer_completion_invalidates_commitment_and_replacement_takes_full_time(self):
        ada = Staff("Ada", "workshop", (67, 0, 95, 0), NEUTRAL)
        ben = Staff("Ben", "workshop", NEUTRAL, (-200, -200, -200, -200))
        run = Simulation(Scenario(staff=(ada, ben), repair_targets=("canoe rack", "supply cart")))
        run.advance(80 * MINUTE)
        self.assertEqual(run.snapshot()["minds"]["Ada"]["repair_commitment"]["target"], "canoe rack")
        run.advance(35 * MINUTE)
        rack_done = Event(115 * MINUTE, "Ben", "completed", "work",
                          "target=canoe rack damaged -> repaired")
        self.assertIn(rack_done, run.history)
        self.assertEqual(run.snapshot()["minds"]["Ada"]["repair_commitment"]["target"], "canoe rack")

        run.advance(30 * MINUTE)
        self.assertIn(Event(145 * MINUTE, "Ada", "abandoned", "work",
                            "target=canoe rack no longer damaged"), run.history)
        self.assertIn(Event(145 * MINUTE, "Ada", "started", "work", "target=supply cart"), run.history)
        self.assertIsNone(run.snapshot()["minds"]["Ada"]["repair_commitment"])
        self.assertEqual(run.snapshot()["active"]["Ada"]["ends_at"], 245 * MINUTE)
        run.advance(DAY)
        self.assertEqual([event for event in run.history
                          if event.phase == "completed" and event.action == "work"], [
            rack_done,
            Event(245 * MINUTE, "Ada", "completed", "work", "target=supply cart damaged -> repaired"),
        ])

    def test_repaired_target_rejects_repeat_and_remains_repaired(self):
        staff = Staff("Ada", "workshop", (0, 0, 95, 0), (-200, -200, 0, -200))
        run = Simulation(Scenario(staff=(staff,), repair_targets=("trail sign",)))
        self.assertEqual(run.snapshot()["repair_states"], {"trail sign": "damaged"})
        run.advance(100 * MINUTE)
        self.assertEqual(run.snapshot()["repair_states"], {"trail sign": "repaired"})
        self.assertFalse(run.submit("Ada", Request("work", target="trail sign")))
        self.assertEqual(run.history[-1], Event(6000, "Ada", "failed", "work", "repair target is unavailable"))
        run.advance(DAY)
        self.assertEqual(run.snapshot()["repair_states"], {"trail sign": "repaired"})
        self.assertEqual([event.phase for event in run.history if event.action == "work"],
                         ["started", "completed", "failed"])

    def test_repair_availability_is_learned_at_the_workshop(self):
        staff = Staff("Ada", "commons", (0, 0, 95, 45), NEUTRAL)
        empty = Simulation(Scenario(staff=(staff,), repair_targets=()))
        damaged = Simulation(Scenario(staff=(staff,), repair_targets=("trail sign",)))
        for run in (empty, damaged):
            run.advance(599)
            self.assertNotIn("work", run.snapshot()["minds"]["Ada"]["memory"])
        self.assertEqual(empty.history, damaged.history)
        empty.advance(1)
        damaged.advance(1)
        self.assertIn(Event(600, "Ada", "redirected", "work", "no damaged targets observed"), empty.history)
        self.assertIn(Event(600, "Ada", "started", "work", "target=trail sign"), damaged.history)

    def test_autonomous_contention_changes_another_agents_choice(self):
        first = Staff("First", "workshop", (0, 0, 95, 0), NEUTRAL)
        second = Staff("Second", "commons", (0, 0, 95, 45), NEUTRAL)
        contested = Simulation(Scenario(staff=(first, second)))
        available = Simulation(Scenario(staff=(second,)))
        for run in (contested, available):
            run.advance(10 * MINUTE)
            self.assertIn(Event(0, "Second", "started", "move", "to=workshop goal=work"), run.history)
        self.assertIn(Event(0, "First", "started", "work", "target=canoe rack"), contested.history)
        self.assertIn(Event(600, "Second", "redirected", "work", "resource occupied"), contested.history)
        self.assertIn(Event(600, "Second", "started", "move", "to=commons goal=leisure"), contested.history)
        self.assertIn(Event(600, "Second", "started", "work", "target=canoe rack"), available.history)

    def test_unobserved_supply_does_not_change_choice_until_arrival(self):
        staff = Staff("Ada", "commons", (90, 0, 0, 45), NEUTRAL)
        empty = Simulation(Scenario(staff=(staff,), servings=0))
        stocked = Simulation(Scenario(staff=(staff,), servings=1))
        for run in (empty, stocked):
            run.advance(599)
            self.assertNotIn("meal", run.snapshot()["minds"]["Ada"]["memory"])
        self.assertEqual(empty.history, stocked.history)
        empty.advance(1)
        stocked.advance(1)
        self.assertIn(Event(600, "Ada", "redirected", "meal", "no servings observed"), empty.history)
        self.assertIn(Event(600, "Ada", "started", "meal"), stocked.history)

    def test_failed_actions_report_reasons_without_world_effects(self):
        staff = Staff("Ada", "commons", NEUTRAL, NEUTRAL)
        run = Simulation(Scenario(staff=(staff,)))
        before = run.snapshot()
        self.assertFalse(run.submit("Ada", Request("meal")))
        self.assertFalse(run.submit("Ada", Request("move", "lake")))
        self.assertEqual(run.snapshot(), before)
        self.assertEqual(run.history, (
            Event(0, "Ada", "failed", "meal", "wrong location"),
            Event(0, "Ada", "failed", "move", "destination is not adjacent"),
        ))
        self.assertTrue(run.submit("Ada", Request("move", "kitchen")))
        run.advance(17)
        before = run.snapshot()
        self.assertFalse(run.submit("Ada", Request("meal")))
        self.assertEqual(run.snapshot(), before)
        self.assertEqual(run.history[-1], Event(17, "Ada", "failed", "meal", "already occupied"))
        run.advance(583)
        self.assertIn(Event(600, "Ada", "completed", "move", "kitchen"), run.history)

    def test_reproducibility_across_advance_chunks_with_simultaneous_events(self):
        direct = Simulation(Scenario(days=4), seed=42)
        chunked = Simulation(Scenario(days=4), seed=42)
        for run in (direct, chunked):
            self.assertFalse(run.submit("Ada", Request("meal")))
            self.assertTrue(run.submit("Ada", Request("move", "kitchen")))
            run.advance(0)
            self.assertEqual([event.staff for event in run.history if event.phase == "started"],
                             ["Ada", "Ben", "Clara"])
            self.assertFalse(run.submit("Clara", Request("leisure")))
        direct.advance(4 * DAY)
        for _ in range(96):
            chunked.advance(3600)
        self.assertEqual(direct.snapshot(), chunked.snapshot())
        self.assertEqual(direct.history, chunked.history)


if __name__ == "__main__":
    unittest.main()

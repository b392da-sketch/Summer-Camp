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
            self.assertEqual({event.action for event in completed if event.staff == staff}, activities)
        self.assertTrue(all(event.action in activities for event in run.history))
        self.assertGreater(state["repairs"], 0)
        self.assertEqual(state["repairs"], sum(event.action == "work" for event in completed))
        meals_started = sum(event.action == "meal" and event.phase == "started" for event in run.history)
        self.assertGreater(meals_started, 0)
        self.assertEqual(state["servings"], 200 - meals_started)

    def test_work_interruption_resumes_only_remaining_duration(self):
        run = Simulation(seed=42)
        run.advance(219 * MINUTE)
        self.assertIn(Event(115 * MINUTE, "Clara", "interrupted", "work", "hunger, 2400s remaining"),
                      run.history)
        self.assertIn(Event(180 * MINUTE, "Clara", "resumed", "work"), run.history)
        self.assertTrue(any(event.staff == "Clara" and event.action == "meal"
                            and event.phase == "completed" for event in run.history))
        self.assertEqual(run.snapshot()["repairs"], 0)
        run.advance(MINUTE)
        self.assertIn(Event(220 * MINUTE, "Clara", "completed", "work", "repairs=1"), run.history)

    def test_interrupted_work_waits_if_another_staff_member_takes_bench(self):
        ada = Staff("Ada", "workshop", (67, 0, 95, 0), NEUTRAL)
        ben = Staff("Ben", "workshop", NEUTRAL, (-200, -200, -200, -200))
        run = Simulation(Scenario(staff=(ada, ben)))
        run.advance(80 * MINUTE)
        self.assertIn(Event(15 * MINUTE, "Ada", "interrupted", "work", "hunger, 5100s remaining"),
                      run.history)
        self.assertIn(Event(15 * MINUTE, "Ben", "started", "work"), run.history)
        self.assertIn(Event(80 * MINUTE, "Ada", "redirected", "work", "resource occupied"), run.history)
        self.assertFalse(any(event.phase == "resumed" for event in run.history))
        self.assertEqual(run.snapshot()["minds"]["Ada"]["work_remaining"], 5100)

    def test_autonomous_contention_changes_another_agents_choice(self):
        first = Staff("First", "workshop", (0, 0, 95, 0), NEUTRAL)
        second = Staff("Second", "commons", (0, 0, 95, 45), NEUTRAL)
        contested = Simulation(Scenario(staff=(first, second)))
        available = Simulation(Scenario(staff=(second,)))
        for run in (contested, available):
            run.advance(10 * MINUTE)
            self.assertIn(Event(0, "Second", "started", "move", "to=workshop goal=work"), run.history)
        self.assertIn(Event(0, "First", "started", "work"), contested.history)
        self.assertIn(Event(600, "Second", "redirected", "work", "resource occupied"), contested.history)
        self.assertIn(Event(600, "Second", "started", "move", "to=commons goal=leisure"), contested.history)
        self.assertIn(Event(600, "Second", "started", "work"), available.history)

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

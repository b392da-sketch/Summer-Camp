# M1 autonomous camp life

Run the six-person fixture with `python3 -m summer_camp --scenario m1 --seed 42`. Add `--summary-only` for counts. The run lasts four simulated days by default. Seven days remain supported and normal playback still advances 16 simulated seconds per real second.

## Architecture

- `reference_camp.py` supplies the provisional roster, public paths, finite jobs, and initial supplies. Staff profiles give role, facility responsibilities, skills, and sleep preferences. A custom scenario can supply a different roster and layout.
- `cognition.py` scores intentions from unmet needs, personal preferences, responsibilities, current time, and observed conditions. Staff may visit a facility to inspect it on the strength of a known responsibility. A stale observation of unavailable food or work can prompt a recheck after two hours. Completed jobs stay completed, so a worker who has observed no eligible unfinished jobs has no further work reason to make that trip.
- `world.py` describes each job by identity, facility, duration, capability, and outcome. Active work owns the facility's single preparation slot and reserves the batch's ingredients. Availability checks precede the single change that starts an action. Interruption or cancellation removes the action and releases both reservations. Successful completion applies the outcome once. A batch exchanges reserved ingredients for servings, and eating consumes a serving at meal start.
- `simulation.py` keeps M0's deterministic scheduling. A worker's interruption retains time remaining for that target. Resumption rechecks location, capability, reservations, and availability. A worker drops a stale commitment on observing peer completion. Cancellation discards progress. Job observations contain only information visible at the worker's current facility. At the same simulated time, the next scheduled callback sees changes already made by earlier callbacks.
- Sleep is a continuous stay in the sleeping quarters. Fatigue falls in proportion to simulated time spent asleep, with a floor at zero. The fatigue threshold for initiating sleep rises with distance from the individual's preferred bedtime. A sufficiently tired staff member can sleep outside that window. Hunger rises more slowly during sleep. Meals receive a time-of-day preference and are also possible outside meal windows.

## Four-day measurements

Reproduce the table with `python3 -m summer_camp --scenario m1 --seed SEED --summary-only`. Counts are completed activities. A sleep bout underway at the horizon is excluded from the completed count.

| Seed | Events | Meals | Sleep bouts | Leisure bouts | Jobs completed | Servings left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 786 | 77 | 19 | 76 | 12 | 35 |
| 7 | 798 | 77 | 18 | 77 | 12 | 35 |
| 42 | 808 | 78 | 18 | 77 | 12 | 34 |

The provisional test bands are 8–16 completed meals and 3–4 completed sleep bouts per person across four days. At least three quarters of sleep starts on days 3–4 fall between 16:00 and 05:00 across midnight. In these runs, individuals completed 12–14 meals, 3–4 sleep bouts of 7.5–8 hours, and 12–13 leisure bouts. All three runs completed four repairs, two cabins, and six meal batches. The tests check unique job completion and conservation of ingredients and servings. They permit unfinished jobs at the horizon.

## Sample trace

Selected events from seed 42. The CLI command above prints the full four-day history.

```text
Day 1 01:30:00  Taylor completed   prepare (target=north cabin pending -> ready)
Day 1 01:50:00  Morgan completed   prepare (target=meal batch 1 pending -> cooked, ingredients -3, servings +16)
Day 1 03:35:00  Cameron completed   prepare (target=canoe rack pending -> repaired)
Day 1 16:25:00  Cameron started     sleep (duration=27000s)
Day 2 04:20:00  Avery  completed   prepare (target=meal batch 3 pending -> cooked, ingredients -3, servings +16)
Day 2 17:35:00  Morgan started     sleep (duration=27900s)
Day 3 15:10:00  Avery  completed   prepare (target=meal batch 5 pending -> cooked, ingredients -3, servings +16)
Day 3 20:50:00  Jordan started     sleep (duration=27900s)
Day 4 05:30:00  Morgan completed   prepare (target=meal batch 6 pending -> cooked, ingredients -3, servings +16)
Day 4 19:20:00  Taylor started     sleep (duration=28800s)
```

The initial roster starts awake at midnight with seeded needs, so the first day can show off-hour work and sleep. The fixture uses fixed travel times, one preparation slot per facility, one shared kitchen inventory, and finite supplies with no replenishment. Staff observe on arrival and at decision points. Sleep durations, need rates, and resource sizes are provisional tuning values. Work interruption and peer takeover are exercised in controlled tests. They need not occur in every reference run.

# M6 environmental maintenance

Run `python3 -m summer_camp --scenario m6 --seed 0` for the full four-day trace. Add `--summary-only` for totals or `--days 7` for the longest scenario. Normal playback remains 16 simulated seconds per real second.

## Local knowledge and report-driven visits

A staff member can notice the bin at an ordinary decision point or upon arrival in the service yard. The yard must be the person's actual node and have a light level of at least two after the focus penalty. Sleeping and travelling staff are ineligible. Requiring the same node excludes views through adjacent locations. Deliberate local inspection retains M5's lighting bonus.

Each person keeps the last visible condition and when they checked it. An unchanged check refreshes the time without creating another testimony reference. Their first visible tipped state and subsequent visible changes can enter the bounded M3 sensory memory. The cache contains no physical revision. A person who misses the intervening cleanup can see the bin tipped again without knowing that it was a different episode.

A credible M4 notice or inspection report of a tipped bin may prompt a service-yard visit for up to 75 minutes from the observation. The original witness, features, and timestamps stay intact. Existing one-hop relay and duplicate rules apply. An arriving worker needs a fresh ordinary notice or a successful inspection before choosing to right the bin. Seeing it upright abandons the plan. If a deliberate inspection cannot establish the condition, that visit ends. Needs and other work can take precedence.

## Physical actions and timing

- The container revision increases on every actual upright–tipped transition. A 30-minute righting action reserves the worker and the container using a separate action ticket bound to that revision. The world validates location, repair capability, availability, and condition before issuing a reservation.
- Completion checks the active action, reservation, timestamp, and revision before restoring the container. Cancellation releases the slot and discards progress. Interruption for hunger or fatigue releases it and keeps the remaining work for that revision only. An obsolete commitment is rejected, after which a new righting action can start at full duration. M1's permanent preparation jobs retain their own records.
- The reference layout places the service yard on the kitchen approach. The commons–service-yard link takes ten minutes in either direction, or fifteen when service-yard wetness is at least three at departure. The world fixes the arrival at action creation. Mid-trip weather changes do not alter it. Staff can remember the elapsed crossing after arrival. Planning still uses the public graph without reading remote wetness.
- Existing FIFO callbacks resolve ties. A forage after completed righting can tip the bin under a new revision. A forage before righting can consume scraps from the already tipped bin without tipping it again. A departure after a weather callback uses the new wetness. Existing wake tickets and righting reservations reject callbacks for prior actions.

## Four-day reference measurements

Each seed reproduced its full history and final snapshot with one advance and with 2,137-second chunks. Meals, sleep, leisure, preparation, conversations, and wildlife continued, with edible food conserved. Wet crossings count departures that received the fifteen-minute duration.

| Seed | Events | Bin notices | Tips | Autonomous rightings | Wet crossings | Meals | Sleep bouts | Leisure bouts | Preparation jobs | Conversations | Servings left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1764 | 48 | 6 | 6 | 11 | 76 | 19 | 74 | 13 | 94 | 36 |
| 7 | 1789 | 56 | 7 | 7 | 49 | 72 | 18 | 77 | 13 | 121 | 40 |
| 42 | 1746 | 44 | 5 | 5 | 36 | 76 | 18 | 77 | 13 | 107 | 36 |

In seed 0, day 1, the raccoon tips the bin at 03:40. Robin notices it at 05:45, starts righting it at 07:15, and finishes at 07:45. Another forage tips it again at 10:30. On day 4, Morgan starts a wet crossing at 03:15 and reaches the service yard at 03:30. All three seeds produced autonomous maintenance.

## Controlled causal comparisons

**Maintenance.** Run `python3 -m unittest discover -s tests -p test_maintenance.py -k autonomous_cleanup`. One successful cooking batch creates scraps. The raccoon tips the bin at 00:40 in both runs. With the yard lit, Morgan notices it at 00:45 and voluntarily rights it by 01:15. At 02:30 the raccoon forages again and tips the restored bin. In the dark run, Morgan never makes that discovery or starts cleanup. The same second forage consumes the remaining scrap without creating another tip.

**Movement.** Run the same test module with `-k wet_route` or `-k uninformed_route`. At 06:00, the weather update takes wetness from two to four. A departure first in FIFO takes ten minutes. A departure after the update takes fifteen. In the mid-trip case, wetness falls from three to two at 12:00, but the trip booked at 11:55 still arrives at 12:10. The uninformed-route test also verifies that two travelers select the same meal route despite different physical durations.

Durations, thresholds, and choice scores are provisional. M6 covers one bin and one wet link. Lid securing, dynamic detours, and broader maintenance work orders remain deferred.

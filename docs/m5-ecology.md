# M5 environmental ecology

M5 adds an independently evolving physical environment to the camp. Run `python3 -m summer_camp --scenario m5 --seed 0` for the full trace. The fixture defaults to four days and accepts up to seven. Normal playback remains 16 simulated seconds per real second.

## Architecture and physical rules

- **Weather.** The reference starts breezy and dry with zero wetness. Every three hours, the interval that just elapsed adds two wetness levels if it was raining or removes one if it was dry, bounded from zero to four at exposed nodes. Then the new conditions take effect. The consecutive wind weights for calm, breezy, and gusty are `7/3/0` from calm, `2/5/3` from breezy, and `0/4/6` from gusty. Rain persists with probability 0.7 and starts from dry with probability 0.2. A dedicated weather RNG is seeded independently of the staff. At the horizon, the final elapsed interval updates wetness without drawing new conditions or attempting a gust.
- **Shutter.** On entering gusty conditions, the world attempts one impulse on an exposed fitting. The current latch security and the open/closed position are separate world fields. A valid impulse toggles the position. A completed M1 securing job changes only security. Failed, cancelled, and interrupted work cannot secure it. Manually queued M3 impulses check the same live security. M5 uses no nightly disturbance queue. M3 and M4 retain their original fixture behaviour.
- **Raccoon and refuse.** A successful cooking batch adds two scrap units, capped at six, to the outdoor service yard adjoining the kitchen. This waste ledger is separate from ingredients, servings, and reservations. The raccoon starts at the woodland den. It evaluates hunger and accessible scraps after 30 minutes at a node. Rain raises the hunger threshold for leaving shelter from three to six. The animal follows the configured wildlife trails, advancing one timed leg at a time. It has no node location during transit. Arrival checks the active transit record. At accessible refuse, it can consume one scrap per successful forage. The first contact tips the container. Later foraging leaves it tipped and emits no repeat tipping event. No new leg starts if it would end after the horizon.
- **Sensory projection.** An authoritative incident records the actual cause, target, and result. A separate stimulus carries just time, spatial origin, possible visual recognition, and strength. M3 projects that stimulus using light, sightlines, acoustic loss, attention, and wake/travel eligibility. A faint noise carries no source identity or exact cause. Local inspection can reveal a secure latch, a tipped bin, or wet ground, using present conditions. M4 reports and relays only witness-local evidence.
- **Ordering.** Weather, wildlife, and staff callbacks use the same FIFO clock. A securing job that completes before the gust callback suppresses the impulse. If the gust wins the tie, it can move the shutter before it is secured. Every successful incident and its evidence are resolved together. Neither the weather update nor the animal's decisions query whether a counselor can observe them.

The weather table, timings, animal thresholds, and sensory strengths are provisional. Wet ground has no travel penalty. The fixture has one animal and fixed habitat, with no animal population dynamics or complex weather effects.

## Four-day measurements

All three runs completed 32 weather updates and conserved edible food. Full histories and final states matched between one advance and 2,137-second chunks.

| Seed | Events | Animal legs | Forages | Incidents | Inspections | Meals | Sleep bouts | Leisure bouts | Jobs | Conversations | Servings left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1343 | 14 | 12 | 1 | 1 | 77 | 19 | 76 | 13 | 105 | 35 |
| 7 | 1413 | 20 | 12 | 1 | 2 | 78 | 18 | 77 | 13 | 118 | 34 |
| 42 | 1401 | 18 | 12 | 1 | 1 | 79 | 18 | 78 | 13 | 121 | 33 |

Each reference incident was a container tipping. Staff secured the shutter before any weather-driven impulse could move it in these seeds. The controlled runs exercise the loose-shutter path and demonstrate that securing it can also remove a downstream investigation.

## Controlled causal trace

Reproduce the following sequence with `python3 -m unittest discover -s tests -p test_ecology.py -k controlled_wind`. The setup completes an ordinary cooking job and sends the cook to bed. The weather, foraging, and Scout's response to the clatter are autonomous. The final inspection is a controlled input to verify what a later visitor can discover.

| Simulated time | Result |
| --- | --- |
| 00:05 | Cooking completes and produces four servings and two scrap units. |
| 00:25–00:30 | The cook goes to sleep. The raccoon leaves the den along its ten-minute trail toward the scraps. |
| 00:40 | The raccoon arrives, consumes one scrap, and tips the container. Neither staff member perceives the event. |
| 02:30 | The raccoon consumes the remaining scrap. The tipped container stays tipped and produces no new tipping event. |
| 03:00 | Wind changes from breezy to gusty and opens the loose shutter. Scout hears a clatter toward the commons without identifying its cause. |
| 03:10–03:15 | Scout arrives via ordinary travel and inspects the loose latch. |
| 03:40 | A later service-yard inspection reveals the tipped container. It supplies no evidence of what tipped it. |

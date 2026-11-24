# M3 environmental perception

M3 adds private sensory evidence and voluntary investigations to ordinary M2 camp life. Run `python3 -m summer_camp --scenario m3 --seed 42` for the full trace or add `--summary-only` for activity totals. The fixture defaults to four days and accepts up to seven. Normal playback remains 16 simulated seconds per real second.

## Architecture and data boundaries

- **Physical truth.** The world stores each fitting's position. Its loose or secure latch is a persistent fixture condition. A validated impulse moves a loose fitting and creates a transient physical event with a cause, time, source location, and object. The diagnostics show that event. Neither its cause nor its internal identifier is included in staff evidence. A cancelled impulse or an impulse on a secure fitting produces no movement or evidence.
- **Three graphs.** Movement uses the existing camp paths and ten-minute legs. Sightlines are explicit pairs, with same-location vision also possible. Acoustic paths use a separate undirected graph with positive attenuation costs. Sound crosses directly between the commons and boathouse, while walking goes via the shore path. Neither sensory graph grants traversal.
- **Vision and hearing.** Daylight adds three light levels from 06:00 to 18:00. Lamps add local light at the source. Sightline loss and focused attention reduce visible detail. A score of one reveals motion, while three identifies the visible object. Hearing subtracts least-path loss and an attention penalty from source strength. A residual score of two yields an indistinct noise. Four yields a clatter and a direction if the least-loss paths agree on the first hop. Equal paths with conflicting directions yield no direction. A sightline's absence blocks vision across nodes. All constants are engineering approximations.
- **Ordering.** A dedicated seeded random generator chooses one evening opportunity per simulated day in the reference fixture. This stream is separate from staff initialization. Each physical transition and its projection to eligible staff are resolved in a single ordinary clock callback. Simultaneous arrivals, sleep completions, and disturbances follow existing FIFO callback order. Sleeping and travelling staff receive no cues. Arrival never replays an earlier event.
- **Belief and action.** Each recipient retains up to eight evidence records with tentative interpretations. A directional or visual cue can offer one investigation goal for up to 75 minutes. Curiosity affects its priority alongside ordinary needs. Evidence delivery leaves existing actions in progress. At a later decision, a worker can investigate via ordinary movement and a five-minute local inspection. Starting inspection consumes the cue. Abandoning a trip for another decision also clears it. Inspection reveals only currently observable conditions and may be inconclusive. Social claims retain the M2 format and do not relay this evidence.

## Four-day reference measurements

| Seed | Events | Disturbances | Inspections | Meals | Sleep bouts | Jobs | Leisure bouts | Conversations | Servings left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1051 | 4 | 2 | 76 | 19 | 12 | 76 | 99 | 36 |
| 7 | 1094 | 4 | 3 | 78 | 18 | 12 | 77 | 104 | 34 |
| 42 | 1101 | 4 | 2 | 79 | 18 | 12 | 76 | 102 | 33 |

Each seed reproduced its full history and final state in one advance and in 2,137-second chunks. Ingredient, serving, and preparation checks pass for each run.

## Annotated nighttime trace

**Seed 42, day 4**

| Time | Observed result |
| --- | --- |
| 19:28 | A seeded gust closes the loose shelter shutter in the commons. Robin hears a clatter toward the commons. Cameron and Jordan see the shutter move and hear the clatter. Avery is in transit and receives no cue. |
| 19:30–19:40 | Cameron and Jordan choose to inspect and discover the loose latch. That finding supplies no knowledge of what caused the earlier movement. |
| 20:35 | Robin has made no investigation and heads toward the cabins for sleep. |

**Seed 0, day 1**

At 20:12, Avery hears a clatter toward the commons while eating. Morgan sees the shutter move. Avery finishes the meal at 20:35, walks to the commons, and arrives at 20:45. At 20:50 the inspection reveals the loose latch. The event schedule chooses only the gust opportunities. Staff decisions determine whether a cue leads to travel or inspection.

The fixture uses static paths, lamps, and latch conditions. Initial visual attention is represented by a penalty during preparation and conversation. Propagation has no delay, and the model omits sleep interruption, within-path sensing, detailed geometry, automatic interpretation of hidden causes, and sensory reports through social exchanges.

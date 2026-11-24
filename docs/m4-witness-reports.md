# M4 witness reports

Run `python3 -m summer_camp --scenario m4 --seed 42` for the complete four-day trace. Add `--summary-only` for activity totals or `--days 7` for the longest scenario. Normal playback remains 16 simulated seconds per real second.

## Contracts and lifecycle

- **Firsthand memory.** M3 assigns each sensory memory a monotonic observer-local reference. A character can report only one observation that is still in their own eight-record buffer. The immutable payload copies the perceived features and keeps the tentative interpretation separate. It contains no physical cause, diagnostic event ID, or source identity hidden from the witness. A sound's area remains the perceived approximate direction, including an absent direction.
- **Delivery.** M4 reuses M2's five-minute, co-present, consensual encounters. Admission freezes the payload even if later sensory activity evicts it. Completion records a successful topic and delivers once. Refusal or cancellation delivers nothing, preserves the approach cooldown, and allows a future retry. Existing reservations, completion tickets, and job claims use the same paths.
- **Hearsay.** A relay retains the original witness, observation time and features, and first successful report time. It adds the immediate speaker and current delivery time. A relayed delivery cannot be forwarded again. A listener keys retained testimony by witness and witness-local reference. Duplicate deliveries cannot replace the first copy, raise credibility, or refresh investigation. The listener keeps up to 12 accounts and retains a deduplication entry through each account's 18-hour reporting window. Different witnesses remain distinguishable even when they describe similar cues or disagree.
- **Autonomy.** At existing social opportunities, staff consider recent firsthand and one-hop reports. Significance, age, company preference, directed affinity and trust influence the choice. Ordinary obligations, consent, topic rules, and cooldowns still apply. The M4 fixture gives Taylor a slightly higher company preference so another temperament participates in reporting.
- **Assessment and investigation.** The listener can find a report credible, doubt it, or disregard it. A credible report with a directional or visual area can offer one investigation before the original observation is 75 minutes old. Reports and firsthand evidence compete with ordinary needs. An investigation keeps one provenance while travelling and uses ordinary movement and a five-minute local inspection. A new direct inspection can compare a previously reported latch condition. It cannot establish the cause of an earlier sound. Ambiguous cues without an area do not create a destination.

Follow-up questions, passive overhearing, detailed misunderstandings, and relationship recalibration are deferred. The simulation's full history and snapshots remain diagnostics.

## Four-day measurements

Testimony and relay columns count unique successful deliveries. All runs had four physical disturbances. The three seeds reproduced full histories and final states in one advance and in 2,137-second chunks. Each run conserved ingredients and servings.

| Seed | Events | Conversations | Firsthand deliveries | Relays | Inspections | Meals | Sleep bouts | Leisure bouts | Jobs | Servings left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1096 | 106 | 6 | 2 | 2 | 78 | 19 | 76 | 12 | 34 |
| 7 | 1150 | 121 | 3 | 4 | 1 | 77 | 18 | 77 | 12 | 35 |
| 42 | 1139 | 123 | 2 | 1 | 1 | 79 | 18 | 77 | 12 | 33 |

The reference runs produced spontaneous reports and relays. Their inspections came from firsthand cues. The controlled trace below demonstrates a report causing an investigation within the shorter action window.

## Annotated causal trace

The test `test_autonomous_report_changes_decision_without_transferring_firsthand_knowledge` compares the same seeded camp and physical disturbance with testimony enabled or disabled. Staff initiate their own conversation and travel.

| Time | Event |
| --- | --- |
| 00:10 | A gust moves a shutter at the boathouse. Avery hears a clatter toward the shore path. Morgan is still travelling when the disturbance resolves and hears nothing. |
| 00:15 | Avery approaches Morgan during leisure. |
| 00:20 | Morgan receives Avery's attributed observation, with the shore path as the heard direction and no source identification. |
| 01:10 | Receptive Morgan finishes leisure and decides to walk to the shore path. |
| 01:20–01:25 | Morgan arrives, inspects, and finds nothing conclusive. The boathouse shutter remains in the same physical state as in the control. |
| 02:00 | With testimony disabled, Morgan has made no report-driven trip. An indifferent Morgan receives the account and also makes no trip. Casey receives no account. |

In the six-person reference with seed 42, Taylor tells Avery about a moving shutter at 09:40 on day 2. At 13:00, Avery relays Taylor's observation to Jordan, keeping Taylor as the witness. The controlled relay test also checks duplicate paths and confirms that a relay recipient cannot forward that account again.

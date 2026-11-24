# M2 autonomous social life

Run `python3 -m summer_camp --scenario m2 --seed 42` for the full four-day trace. Use `--summary-only` for totals or `--days 7` for the longest supported scenario. The fixture uses the six provisional adults and facilities from M1. M0 and M1 retain their original settings. Normal playback remains 16 simulated seconds per real second.

## Architecture

- **Availability and scheduling.** Two staff can talk only at the same facility while idle or at leisure. Sleep, travel, meals, focused work, and existing conversations occupy the action slot. A five-minute conversation reserves both slots together and pauses any leisure in progress. M2 checks for opportunities at decision points and during leisure. One callback owns completion. Completion or disengagement restores the remaining leisure and releases both conversation slots. Reservation identities and wake tickets make stale callbacks harmless. Encounters must fit within the scenario.
- **Autonomy.** Staff with an appetite for company can head to the commons when ordinary needs and responsibilities permit it. Autonomous encounters begin with a greeting or a request about an observed pending job. The semantic exchange API also supports asking about a job or reporting an observation. Either person may refuse a conversation. Per-peer cooldowns, breaks between autonomous approaches, and one completed substantive exchange per sender, peer, and topic keep exchanges from immediately repeating. A cancelled exchange can be retried after the approach cooldown.
- **Knowledge and relationships.** A completed exchange delivers one claim to its intended listener. It carries the source, facility, job, asserted state, observation time, and delivery time. The speaker's own memory supplies the content, including stale information. A later direct inspection can confirm or contradict the claim. Familiarity, affinity, and practical trust are private directional values. Greeting affinity depends on the participant's preference. Declined help can lower the requester's affinity, and personal confirmation can increase trust. Co-presence alone changes no values.
- **Help.** A listener can accept, decline, or defer after agreeing to converse. Acceptance creates a four-hour actor-local intention that can lose to urgent needs. It can prompt travel, but fresh local evidence and M1's existing work validator govern job start and completion. The helper's commitment can expire, become obsolete on inspection, or be fulfilled by their own completed work. The requester's record preserves the response they heard. Later completion requires the requester to observe it or receive a report.

## Four-day reference measurements

These are completed activity counts from `python3 -m summer_camp --scenario m2 --seed SEED --summary-only`. A conversation counts once per pair. Each whole run and its chunked counterpart produced identical histories and final states.

| Seed | Events | Conversations | Meals | Sleep bouts | Leisure bouts | Jobs | Servings left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1047 | 97 | 77 | 19 | 75 | 12 | 35 |
| 7 | 1068 | 107 | 77 | 18 | 77 | 12 | 35 |
| 42 | 1071 | 103 | 79 | 18 | 76 | 12 | 33 |

## Annotated causal trace

The controlled comparison in `test_autonomous_conversation_changes_work_and_leaves_third_party_uninformed` uses the same starting roster and job in both runs, with social interaction disabled in the control. Neither run submits conversation or work actions.

| Simulated time | Event or observation |
| --- | --- |
| 00:00 | Alex inspects the boathouse and sees the pending rack repair, then heads to the commons for leisure. Bo starts leisure in the commons. Casey goes to sleep in the cabins. |
| 00:10 | Alex arrives and approaches Bo during leisure. Bo agrees to talk. |
| 00:15 | The conversation completes. Bo receives Alex's attributed pending report, observed at 00:00, and accepts the request. Bo resumes leisure. |
| 01:00 | Bo finishes leisure and heads to the boathouse. |
| 01:10 | Bo observes the pending repair and starts work through the M1 validator. |
| 01:40 | Bo completes the repair. The rack changes to repaired. Bo's commitment is fulfilled. |
| 02:00 | With social interaction enabled, the rack is repaired. In the control it is still pending. Casey has received no claim and Alex still remembers the rack as pending. |

The model uses facility-level presence, provisional personality values, and single-topic conversations. Ordinary needs continue to accrue during exchanges. A participant can decline at admission or explicitly disengage. There is no mid-exchange needs check, overhearing, forwarding, or dialogue prose. Deferred requests have no automatic follow-up. Repeated greetings currently increase affinity for sociable participants. Calibrating that effect is deferred.

# Summer Camp

M0 is a headless reference simulation of ordinary camp life. It runs on Python 3.12 with the standard library.

```sh
python3 -m unittest discover -s tests -v
python3 -m summer_camp --days 4 --seed 42 --summary-only
python3 -m summer_camp --days 1 --seed 42 --demo-failure
```

The last command prints a full camp-day trace and includes a deliberate invalid meal request. See the [annotated trace](docs/sample-day.md) for an excerpt.

## Architecture

| Module | Responsibility |
| --- | --- |
| `clock.py` | Integer simulated seconds and a FIFO tie-breaker for callbacks due at the same time. A separate playback adapter converts caller-supplied elapsed time at 16:1 by default and supports pause and rate changes. |
| `world.py` | Owns locations, active actions, shared resource capacity, servings, and the condition of individual repair targets. Validates requests and applies their consequences. |
| `cognition.py` | Keeps separate needs, preferences, local observations, remembered facts, and work commitments for each staff member. Ranks available activities using those inputs and routes through the posted map. |
| `simulation.py` | Delivers observations, resolves requests, and schedules the next action completion or decision. Exposes ordered event history and detached state snapshots for tests and diagnostics. |

To configure a scenario, pass a `Scenario` with a roster of `Staff` records to `Simulation`. Staff can have explicit starting locations, needs, and preferences. Missing needs and preferences are drawn from the seeded generator in roster order. Subsequent decisions use deterministic scoring and stable activity ordering. The first wake follows roster order. Later wakes at the same timestamp follow enqueue order, including any reservations or releases made by an earlier wake at that timestamp.

Call `advance(seconds)` for headless runs or pass it to `Playback` for host-driven playback. Four simulated days take six real hours at normal playback. Scenarios can run for one to seven days. Both `Simulation.advance` and `Playback.update` report the seconds actually applied. Simulation advancement stops at the configured horizon, so activities underway at that point can remain incomplete in the final snapshot.

## M0 assumptions

The camp uses a four-location graph with ten-minute links. The layout is public. Staff learn live supplies and occupancy by visiting the relevant location. They can use recent observations while away and may act on stale beliefs. The world checks current prerequisites again when accepting a request. Meals consume a serving at the start. The workshop starts with a finite list of damaged objects, configurable through `Scenario.repair_targets`. Staff discover damaged targets at the workshop. A completed repair changes one target to `repaired` for the rest of the scenario. Hunger can interrupt bench work. The staff member retains the remaining duration for that particular target and must find both a damaged target and a free bench to resume. Progress is private to the staff member. Another staff member starts a full repair and can invalidate the first staff member's commitment, which is abandoned upon observing the completed repair.

The roster, need rates, resource capacities, and memory windows are prototype values. There is no conversation model or cross-session persistence. Reproduction consists of rerunning the same scenario, seed, and timed inputs. The event history is a diagnostic record. This milestone leaves rendering, engine selection, detailed geography, multiplayer, and horror or combat systems for later work.

## M1 camp-life fixture

M1 is opt-in. The default command still runs M0.

```sh
python3 -m summer_camp --scenario m1 --seed 42 --summary-only
python3 -m summer_camp --scenario m1 --seed 42
python3 -m unittest discover -s tests -v
```

The M1 fixture defaults to four simulated days and accepts `--days 1` through `--days 7`. See [M1 architecture, metrics, and sample trace](docs/m1-camp-life.md).

## M2 social-life fixture

```sh
python3 -m summer_camp --scenario m2 --seed 42
python3 -m summer_camp --scenario m2 --seed 42 --summary-only
```

M2 is opt-in and defaults to four days. See the [architecture, metrics, and causal trace](docs/m2-social-life.md).

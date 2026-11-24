# Camp-day event trace

Generated with `python3 -m summer_camp --days 1 --seed 42 --demo-failure`. Times are simulated. Selected lines from the run:

```text
Day 1 00:00:00  Ada    failed      meal (wrong location)
Day 1 00:45:00  Ben    started     move (to=kitchen goal=meal)
Day 1 00:45:00  Clara  completed   leisure
Day 1 00:45:00  Clara  started     move (to=workshop goal=work)
Day 1 00:55:00  Ada    completed   move (kitchen)
Day 1 00:55:00  Ada    started     meal
Day 1 00:55:00  Ben    completed   move (kitchen)
Day 1 00:55:00  Ben    started     meal
Day 1 00:55:00  Clara  completed   move (workshop)
Day 1 00:55:00  Clara  started     work
Day 1 01:20:00  Ben    completed   meal
Day 1 01:20:00  Ben    started     move (to=commons goal=work)
Day 1 01:40:00  Ada    started     rest
Day 1 01:40:00  Ben    completed   move (workshop)
Day 1 01:40:00  Ben    redirected  work (resource occupied)
Day 1 01:40:00  Ben    started     move (to=commons goal=rest)
Day 1 01:50:00  Ben    completed   move (commons)
Day 1 01:50:00  Ben    started     move (to=cabins goal=rest)
Day 1 02:05:00  Clara  completed   move (commons)
Day 1 02:05:00  Clara  started     move (to=kitchen goal=meal)
Day 1 02:15:00  Clara  completed   move (kitchen)
Day 1 02:15:00  Clara  started     meal
Day 1 02:40:00  Clara  completed   meal
Day 1 02:40:00  Clara  started     move (to=commons goal=work)
Day 1 02:50:00  Clara  completed   move (commons)
Day 1 02:50:00  Clara  started     move (to=workshop goal=work)
Day 1 03:00:00  Clara  completed   move (workshop)
Day 1 03:00:00  Clara  resumed     work
Day 1 03:40:00  Ada    completed   rest
Day 1 03:40:00  Ada    started     move (to=commons goal=meal)
Day 1 03:40:00  Clara  completed   work (repairs=1)
Day 1 03:40:00  Clara  started     move (to=commons goal=rest)
1 simulated day(s), 345 events
Completed: leisure=12, meal=23, move=108, rest=10, work=8
Servings left: 177 | Repairs: 8
```

The first line comes from an explicit test input. Ada is at the commons, so the meal request fails before a serving is taken. The rest of the trace comes from autonomous decisions. Ben heads to the workshop while Clara is working there. On arrival he sees the occupied bench and changes his goal to rest. Clara later releases the bench when hunger interrupts her work. After eating, she returns to the workshop, finds a free bench, and completes the forty remaining minutes of work. The repair total changes at completion.

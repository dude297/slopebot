# Experiment Protocol

## Why this exists

Slope has noisy runs and increasing speed. A controller can look better because of one favorable course sequence. Changes must therefore be evaluated across repeated runs.

## Before changing behavior

Write down:

- hypothesis
- parameter/code change
- expected failure mode to improve
- metric expected to move
- possible regression

Example:

> Hypothesis: most current high-speed deaths are overshoot caused by lateral momentum. Adding steering hysteresis should reduce left-right command reversals and improve 25th-percentile survival.

## Baselines

Keep at least two baselines:

### No-steer

```bash
NOSTEER=1 python bot.py 120
```

Use this to validate opening/game-state behavior and to understand natural progression without intervention.

### Current controller

Run the canonical controller with documented parameters.

Record the exact environment values:

```text
KD=
DEAD=
DEBUG=
REACT behavior=
commit SHA=
```

## Recommended run count

For fast iteration:

- 5 runs for smoke testing

For a meaningful comparison:

- at least 20 runs per condition

For a change with high variance:

- 30-50 runs per condition

Do not declare success from the best run.

## Metrics

Primary:

- median survival time
- 25th-percentile survival time
- median score/progression
- death count by category

Secondary:

- command reversals per second
- time spent with no valid track
- track-confidence distribution
- average loop time
- percentage of frames in tunnel/unknown states
- number of emergency/fallback frames

## Death review

For each sampled death inspect the final 2-5 seconds.

Ask in order:

1. Was the game state correct?
2. Was the track geometry correct?
3. Were obstacles/tunnel classified correctly?
4. Was the chosen path physically safe?
5. Was the target reachable given current lateral momentum?
6. Did the controller command the expected direction?
7. Was the command early enough?
8. Did stale/low-confidence perception persist too long?

Classify the earliest causal failure, not merely the final visual event.

## A/B change discipline

Change one major behavior at a time.

Good:

- track persistence 10 -> confidence decay
- controller hold -> hysteresis
- fixed roll -> road-derived roll

Bad:

- new road detector + new controller + new lookahead + new thresholds in one PR

If a bundle is unavoidable, include ablation runs.

## Debug captures

Use `DEBUG=1` selectively because image capture can alter loop timing.

Measure debug and non-debug loop rates separately.

Prefer:

- lightweight telemetry every tick
- sampled screenshots
- dense screenshots only for short controlled experiments

## Regression fixture policy

Whenever a specific scene causes a reproducible bug:

1. preserve a representative frame
2. document the failure
3. add expected output/range
4. fix the algorithm
5. keep the frame as a regression fixture

This prevents the bot from cycling through the same perception bugs.

## Acceptance template for a behavior PR

```text
Hypothesis:
Change:
Commit:
Runs per condition:
Baseline parameters:
Candidate parameters:

Median survival:
25th percentile:
Median progression:
Dominant death category before:
Dominant death category after:

Known regressions:
Representative failure:
Next experiment:
```

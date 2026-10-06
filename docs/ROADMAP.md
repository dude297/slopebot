# Roadmap

This roadmap is ordered by dependency, not novelty.

## Milestone 0 — Reproducible repository

Status: in progress.

Deliverables:

- README and setup instructions
- dependency file
- helper scripts compatible with the current sensor contract
- current-state documentation
- explicit long-term architecture and experiment protocol

Exit criteria:

- a new developer can clone, install, launch, probe, and run the bot without reverse-engineering the repository

## Milestone 1 — Structured telemetry

Goal: stop tuning from anecdotes.

Deliverables:

- stable run IDs
- per-tick structured telemetry
- controller parameters captured with each run
- run summary
- rolling pre-death buffer
- death screenshot linked to run metadata
- basic failure tags

Minimum per-tick fields:

- monotonic timestamp
- game state / phase
- score when available
- `err`
- `near`
- estimated lateral velocity
- command
- track visible/confidence/age
- tunnel flag/confidence
- obstacle distance
- loop duration

Exit criteria:

- for any death, the final seconds can be inspected without rerunning the game
- no major controller parameter is missing from the record

## Milestone 2 — Baseline and death taxonomy

Goal: identify the dominant failure classes.

Run at least:

- 20 no-steer baseline runs
- 20 current-controller runs
- additional runs for any candidate controller change

Classify deaths into categories such as:

- track perception false positive
- track lost
- obstacle missed
- tunnel misclassified
- late steering
- overshoot / momentum
- oscillation
- unknown

Exit criteria:

- at least 80% of reviewed deaths can be assigned a plausible primary category
- the team can state which two failure classes dominate

## Milestone 3 — Offline replay/regression

Goal: make perception development fast and safe.

Deliverables:

- representative recorded frames
- replay harness
- expected geometry/classification ranges
- regression tests for known failures

Exit criteria:

- a perception change can be tested on known scenes without opening Chromium
- previously fixed major perception failures have regression coverage

## Milestone 4 — Perception confidence

Goal: replace binary guesses with confidence-aware behavior.

Deliverables:

- track confidence
- obstacle confidence
- tunnel confidence
- game-state confidence
- stale-track confidence decay
- explicit unknown state

Exit criteria:

- low-confidence perception is visible in telemetry
- planner/controller behavior changes intentionally when confidence is low

## Milestone 5 — Camera roll and road orientation

Goal: handle tilted/rolling scenes robustly.

Approach:

- estimate orientation only from road-consistent geometry
- reject scenery-dominated candidates
- smooth orientation over time
- compare against `th=0` baseline on replay fixtures and live runs

Exit criteria:

- tilted scenes no longer require a fixed zero-roll assumption
- no meaningful increase in false road locks on scenery fixtures

## Milestone 6 — General game-state and score telemetry

Goal: remove the score-1 special case as the only score understanding.

Deliverables:

- robust menu/gameplay/game-over state machine
- general score extraction or reliable score proxy
- speed/progression proxy if score OCR is not sufficiently robust

Exit criteria:

- phase logic does not depend on recognizing only the digit 1
- run summaries contain progression information

## Milestone 7 — Dynamics characterization

Goal: understand how steering actually moves the ball.

Experiments:

- left/right holds of multiple durations
- key release
- counter-steer
- repeated tests at multiple game speeds

Fit a simple empirical response model.

Exit criteria:

- lateral response latency and momentum are quantified
- short-horizon prediction beats naive constant-position prediction

## Milestone 8 — Predictive path/controller

Goal: steer for where the ball will be, not where it is.

Deliverables:

- future safe corridor
- predicted ball trajectory
- steering hysteresis or pulse-width policy
- dynamic lookahead based on speed
- safety constraints against impossible late lane changes

Exit criteria:

- statistically meaningful improvement over the existing controller across repeated runs
- fewer overshoot/late-steering deaths

## Milestone 9 — Automated parameter evaluation

Goal: tune systematically.

Candidate parameters:

- derivative gain
- deadband
- obstacle padding
- track safety margin
- lookahead
- track persistence
- confidence thresholds
- steering pulse/hysteresis values

Optimize:

- median survival
- 25th-percentile survival
- score/progression
- oscillation rate
- perception-related deaths

Exit criteria:

- selected parameters come from repeatable experiments rather than one-off manual tuning

## Milestone 10 — Modularization and CI

Goal: make the system maintainable after behavior stabilizes.

Deliverables:

- split stable interfaces out of `bot.py`
- unit tests
- replay tests in CI
- lint/type checks as appropriate
- documented config

Exit criteria:

- perception/control changes can be reviewed independently
- CI catches sensor-contract and replay regressions

## Milestone 11 — Advanced methods only if justified

Possible later experiments:

- learned segmentation
- imitation learning
- reinforcement learning
- model-predictive control

Entry requirement:

A simpler approach must have reached a clear plateau, and the telemetry/replay stack must be mature enough to evaluate the advanced method fairly.

Do not skip directly to this milestone.

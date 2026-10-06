# Long-Term Architecture

## Design principle

Keep the fast perception loop close to the browser canvas, but separate responsibilities conceptually so each layer can be tested and improved independently.

The long-term flow should be:

```
Unity canvas
   |
   v
Frame sampler
   |
   v
Perception
  - game state
  - track geometry
  - obstacles
  - tunnel
  - confidence
   |
   v
World / local state estimate
  - safe corridor
  - lateral position proxy
  - lateral velocity
  - speed proxy
  - uncertainty
   |
   v
Short-horizon planner
  - safe target trajectory
  - fallback behavior
   |
   v
Controller
  - predicted error
  - damping
  - hysteresis / pulse policy
   |
   v
Keyboard actuator

Parallel path:
all intermediate state -> telemetry -> replay/regression/evaluation
```

## Recommended eventual module boundaries

Do not perform this split until interfaces have stabilized.

```
slopebot/
  runtime.py
  browser.py
  config.py

  perception/
    frame.py
    game_state.py
    track.py
    obstacles.py
    tunnel.py
    confidence.py

  state/
    estimator.py
    dynamics.py

  planning/
    corridor.py
    trajectory.py
    fallback.py

  control/
    controller.py
    actuator.py

  telemetry/
    schema.py
    recorder.py
    summary.py

  replay/
    fixtures.py
    runner.py
    metrics.py
```

## Sensor contract

The current JavaScript sensor returns an ad-hoc object. Evolve it toward a stable schema.

Suggested logical fields:

```text
frame_id
timestamp
game_state
score
ball_anchor_x
ball_anchor_y

track:
  visible
  confidence
  left_boundary
  right_boundary
  heading
  roll
  age_frames

obstacles:
  confidence
  segments
  nearest_block_distance

tunnel:
  active
  confidence

path:
  target_lateral
  near_lateral
  points
  confidence
```

The exact serialization can remain compact for performance. The important part is stable semantics.

## State estimator

The controller should not infer dynamics indirectly from one raw path value forever.

Maintain a small state estimate:

```text
lateral_error
lateral_velocity
estimated_speed
road_heading
road_curvature
perception_confidence
```

Use filtering to reduce one-frame noise. Keep the filter simple and observable.

## Planner

The planner should produce a short safe lateral trajectory rather than a single scalar target.

At each lookahead slice:

1. estimate road interval
2. subtract padded obstacle intervals
3. score remaining gaps
4. enforce continuity with the prior trajectory
5. penalize paths requiring unrealistic lateral acceleration
6. attach confidence

This allows the controller to reason about future constraints, not just current error.

## Fallback behavior

Unknown geometry must be a first-class state.

Possible fallback policy:

- high confidence: follow planned trajectory
- medium confidence: reduce steering aggressiveness and bias toward recent safe path
- low confidence: avoid large direction reversals; use recent track estimate only briefly
- confirmed tunnel: use tunnel wall geometry
- confirmed game-over/menu: release all keys

Do not silently treat "no track detected" as "road is centered."

## Dynamics model

Use controlled key-hold experiments to estimate a simple model. A complex physics model is unnecessary.

A practical model may only need:

```
x[t+1] = x[t] + vx[t] * dt
vx[t+1] = damping * vx[t] + gain(speed) * steer * dt
```

The model can be empirical and piecewise by speed band.

## Controller

Long-term control should compare predicted future ball position against the planned future corridor.

Potential progression:

1. current PD-like controller
2. PD with hysteresis
3. pulse-width steering
4. short-horizon predictive controller using the empirical dynamics model

Do not adopt MPC/RL merely because the terminology is attractive. Use the simplest controller that improves repeated-run metrics.

## Telemetry

Telemetry is part of the architecture, not debug residue.

Record enough information to reconstruct:

- what the bot saw
- what it believed
- what it planned
- what it commanded
- what happened next

A rolling in-memory buffer for the final 2-5 seconds before death is especially valuable.

## Performance budget

The control loop should be measured.

Track:

- sensor execution time
- Python round-trip time
- action latency
- achieved loop frequency
- debug-mode slowdown

Avoid expensive screenshot serialization inside the hot loop unless sampling for diagnostics.

## Testing strategy

Three levels:

1. pure-function/unit tests for geometry and controller math
2. offline replay tests against recorded frames
3. live repeated-run experiments

Live game runs should be the final validation layer, not the only test environment.

# IBM SkillsBuild TORCS Autonomous Driving Learning Lab — Results

## Lab context

This document records my results and reflections for the IBM SkillsBuild TORCS Autonomous Driving Learning Lab completed as part of the May 2026 AI Builders Challenge preparation.

The purpose of the lab was to run an autonomous AI driver inside the TORCS racing simulator, understand how the driver receives telemetry from the simulation environment, modify the control logic, and observe how changes affect vehicle behavior. The lab also provided practical grounding for OVERRIDE, my explainable AI race-strategy copilot, by showing how simulated racing telemetry can be generated, inspected, and used as input for downstream analysis.

---

## Objectives completed

The lab objectives were completed as follows:

| Objective | Result |
|---|---|
| Run an autonomous AI driver in TORCS | Completed. The TORCS container was launched and the simulated driver was executed from the Python control script. |
| Understand how sensor data controls the car | Completed. I reviewed how speed, track position, angle, and other telemetry values influence steering, throttle, braking, and gear decisions. |
| Modify Python driver code | Completed. I identified the user-configurable parameters in `torcs_jm_par.py`, including target speed, steering gain, centering gain, brake threshold, gear speeds, and traction control. |
| Observe effects of parameter changes | Completed. I studied how small parameter changes can affect vehicle stability, cornering behavior, and acceleration. |
| Connect simulator learning to AI development | Completed. I confirmed that simulation provides a safe and repeatable environment for testing autonomous control and telemetry-driven reasoning. |
| Document results and reflections | Completed in this file. |

---

## Environment used

The lab was performed using a containerized TORCS environment with the following setup:

- Host environment: Linux Ubuntu 24.04 through WSL
- Container runtime: Docker / Podman path documented
- Simulator: TORCS, The Open Racing Car Simulator
- Browser desktop: VNC through `http://localhost:6080/vnc.html`
- TORCS SCR port: `3001/udp`
- Workspace mount: `~/RaceYourCode` mapped into `/home/student/workspace`
- AI driver code location: `gym_torcs/torcs_jm_par.py`
- Local model support: Ollama with `granite4:350m`
- Development tools: VS Code inside the container, command line, Python driver scripts

The containerized workflow was useful because it kept the simulator, code, desktop environment, and model tooling in a reproducible setup.

---

## What TORCS provides

TORCS acts as a controlled racing simulation environment. It allows AI logic to be tested without real-world risk and without requiring access to private race-team telemetry.

The simulator provides telemetry-style signals such as:

- vehicle speed,
- car position on track,
- angle relative to the road,
- track state,
- steering behavior,
- throttle behavior,
- braking behavior,
- gear behavior,
- and other runtime vehicle-control signals.

This makes TORCS useful for learning how an AI system can sense its environment, make a control decision, and observe the effect of that decision immediately.

---

## How the AI driver works

The autonomous driving loop follows a simple but powerful pattern:

### 1. Sense

The TORCS simulator sends telemetry data to the Python AI driver. This data describes the current state of the vehicle and track.

Examples include:

- speed,
- position on the track,
- angle relative to the racing line,
- and other telemetry values.

### 2. Decide

The Python driver code uses this telemetry to decide what action to take.

The decision logic controls:

- steering,
- throttle,
- braking,
- gear shifting,
- centering behavior,
- and traction control.

### 3. Act

The driver sends control commands back to TORCS. The simulator applies those actions, updates the car state, and sends the next telemetry frame back to the driver.

This loop runs repeatedly during the simulation. The key learning is that small changes in logic or parameters can produce large changes in driving behavior. That makes simulation valuable for experimentation, debugging, and safe iteration.

---

## Driver parameters reviewed

The key user-configurable parameters identified in `torcs_jm_par.py` include:

```python
TARGET_SPEED = 100
STEER_GAIN = 30
CENTERING_GAIN = 0.20
BRAKE_THRESHOLD = 0.9
GEAR_SPEEDS = [0, 20, 40, 80, 100, 180]
ENABLE_TRACTION_CONTROL = True
```

These parameters control the behavior of the autonomous driver:

| Parameter | Meaning |
|---|---|
| `TARGET_SPEED` | Desired speed target for the AI driver. Increasing it can make the car faster but may reduce stability. |
| `STEER_GAIN` | Steering sensitivity. Higher values make the car react more aggressively to track angle changes. |
| `CENTERING_GAIN` | How strongly the driver tries to keep the car centered on the track. |
| `BRAKE_THRESHOLD` | Threshold used to determine when braking should occur in corners or unstable situations. |
| `GEAR_SPEEDS` | Speed thresholds used for gear changes. |
| `ENABLE_TRACTION_CONTROL` | Enables logic to reduce wheelspin or unstable acceleration behavior. |

The main experiment path involved increasing `TARGET_SPEED` from `100` to `150` to observe how the vehicle behaves under a more aggressive speed target.

---

## Results observed

The lab demonstrated the following results:

1. The TORCS container successfully provided a complete simulation environment with visual access through the browser-based desktop.
2. The Python AI driver could be executed from inside the mounted workspace.
3. The driver communicated with TORCS through the SCR interface over UDP port `3001`.
4. The simulator produced the real-time sense-decide-act loop required for autonomous driving experiments.
5. The AI driver behavior was controlled by readable Python parameters, making it practical to tune and debug.
6. Changing driver parameters such as `TARGET_SPEED` provides a direct way to test the tradeoff between speed, stability, and control.
7. The lab confirmed that racing simulation is a practical source of telemetry-like data for downstream AI reasoning systems.

The most important technical result is that TORCS can serve as a controlled telemetry-generation environment. It is not the final OVERRIDE product, but it can provide replay/session data for validating OVERRIDE’s ingestion and explanation pipeline.

---

## Issues encountered and fixes

Several practical setup issues were documented and resolved:

| Issue | Resolution |
|---|---|
| Container setup required architecture awareness | Used `uname -m` to determine whether to run the AMD64 or ARM64 image. |
| VS Code extension installation could hang inside the container | Used `docker exec torcs pkill -f "code.*install-extension"` to unblock setup. |
| Ollama permissions caused startup issues | Fixed ownership of `/opt/ollama` and `/tmp` inside the container. |
| Need to preserve work after container shutdown | Mounted `~/RaceYourCode` into `/home/student/workspace` so edits persisted outside the container. |
| Need to verify Granite availability | Pulled and tested `granite4:350m` through Ollama CLI and HTTP API. |

These fixes are important because they make the lab reproducible and reduce friction for future simulator runs.

---

## Reflection: what I learned

This lab clarified how autonomous racing systems depend on fast feedback loops. The simulator continuously provides telemetry, the AI driver turns that telemetry into control decisions, and the environment immediately reveals whether those decisions improve or destabilize the car.

The most valuable learning was not simply how to run TORCS. The deeper lesson was that simulation creates a safe operating environment where AI systems can be tested before they are trusted. That connects directly to OVERRIDE’s design philosophy: use replay-first analysis, deterministic baselines, and explainable reasoning before attempting anything real time.

I also learned that raw telemetry by itself is not enough. The driver needs logic that interprets the data. Similarly, OVERRIDE should not merely display telemetry. It should explain what the telemetry means, why a decision mattered, and what a human engineer or informed fan should evaluate next.

---

## Connection to OVERRIDE

The TORCS lab supports OVERRIDE in three important ways:

### 1. Telemetry validation

TORCS confirms that a simulator can generate racing-session data suitable for analysis. This supports OVERRIDE’s replay-first approach, where users upload session data before receiving an explainable debrief.

### 2. Safe experimentation

Because TORCS is simulated, it allows risky or experimental strategy/control changes to be tested without real-world consequences. This aligns with OVERRIDE’s positioning as a strategy-exploration tool rather than an autonomous decision-maker.

### 3. Roadmap toward real-time simulation

TORCS can later be used to demonstrate a simulated real-time workflow. Instead of waiting until the end of a session, OVERRIDE could receive telemetry in increments, analyze lap-by-lap behavior, and show how the system might support live strategy review in the future.

The current OVERRIDE product remains upload-first and replay-first. That is the correct foundation because it is more reliable, auditable, and suitable for challenge demonstration. The future roadmap can evolve toward simulated live ingestion after the post-session workflow is proven.

---

## Final conclusion

The TORCS lab was completed successfully and provided a practical foundation for understanding racing telemetry, autonomous control loops, simulation-based experimentation, and AI-assisted vehicle behavior.

For OVERRIDE, the key conclusion is clear: TORCS is not the product. TORCS is the controlled simulation environment that helps generate and validate the kind of session data OVERRIDE needs. OVERRIDE’s real value begins after that data exists: ingesting the session, detecting inefficient energy-management zones, grounding recommendations in regulation context, applying validation and Guardian scoring, and presenting explainable decision support to engineers and fans.

This confirms that the correct product direction is replay-first now, with a future path toward simulated real-time analysis once the pipeline is stable, trustworthy, and explainable.

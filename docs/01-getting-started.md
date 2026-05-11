# IBM SkillsBuild Hands-On Labs.

- Start with the TORCS Lab → May Challenge lab.
- Work through folders and try things out as you go.
- Use RESULTS.md in your fork to track what you learn.

## 🏁 [TORCS (May Challenge Lab)](https://github.com/IBM-SkillsBuild-AI-Builders-Challenge/hands-on-labs/tree/main/01_torcs_lab)

**Content**

| Name                        | Last commit          |
|-----------------------------|----------------------|
| 00_intro                    | last week            |
| 01_torcs_lab                | 2 weeks ago          |
| 02_setup_guides             | 2 weeks ago          |
| 03_build_your_own_container | 3 days ago           |
| 04_files                    | last week            |
| RESULTS.md                  | Update RESULTS.md    |

## 00. Introduction

**IBM SkillsBuild TORCS Autonomous Driving Learning Lab.**
- Explore autonomous driving concepts using simulation
- Work with TORCS (The Open Racing Car Simulator)
- Use Python‑based AI driver to understand how autonomous systems sense their 
    - environment,
    - make decisions, and 
    - act in real time.
- Learn by building, observing, experimenting, and reflecting.

**Objectives**
- Run an autonomous AI driver in a simulation environment (TORCS).
- Understand how sensor data is used to control
    - Steering
    - Throttle
    - Braking
- Modify Python code that controls a simulated vehicle.
- Experiment with control parameters and observe real-time effects.
- Learn how simulation is used in real-world AI development.
- Document and share your learning through GitHub repository.

**Why use a simulation?**
> TORCS acts a safe, controlled virtual environment forAI development.
- Lets you test ideas safely.
- Run experiments quickly and iteratively.
- Observe edge cases and extreme scenarios without real-world risks.
- Iterate on models and logic before deployment.

## TORCS (The Open Racing Car Simulator)
Open source racing car simulator used in
- Autonomous driving research
- Control system education
- Reinforcement learning experiments.
- AI training and development environments

**Provides the following features**
> TORCS is not a game. It is a **simulation environment** for learning AI control logic.
- Real-time vehicle dynamics/physics
- Multiple race tracks
- Sendor data such as:
    - Speed
    - Position
    - Track angle
- Programmatic interface for controlling the car.

### How the AI driver work
1. **Sense:** Simulator sends data about car and tract to AI.
    - Speed
    - Position on track
    - Angle relative to road
    - Other telemetry
1. **Decide:** The Python code uses logic and parameters to decide
    - How much to steer
    - Whether to accelerate or brake
    - When to change gears
1. **Act:** Simulator sends data about car and tract to AI.
    - The AI sends commands back to TORCS, which moves the car accordingly.

This loop runs many times per second.
Small change in logic or parameters can lead to large change in behavior.
This makes it easy to experiment and iterate quickly. 
Excellent for learning and debugging.

> Focus on learning and experimentation rather than optimization.

**Repository**
Fork first, hands-on learning.
```sh
lab/
└── README.md                # This README (you are here)
└── 01_torcs_lab/
    ├── README_LAB.md        # Lab-specific overview
    ├── 00_intro.md          # Conceptual introduction
    ├── 01_torcs_lab.md      # Step-by-step learning lab
    ├── 02_setup_guides/     # Setup and reference guides
    ├── 03_build_your_own_container/ # Advanced path (optional)
    ├── 04_files/            # TORCS and driver files
    └── RESULTS.md           # Your results and reflections

```
Working inside `lab/torcs_lab` folder.

**Fork** the repository to your own GitHub account.
Navigate to `lab/01_torcs_lab/README_LAB.md` and click the "Fork" button.
- Fork the directory to your own GitHub account.
- Run and modify the AI driver code in the `lab/01_torcs_lab/04_files/` directory.
- Record the results and reflections in the `lab/01_torcs_lab/RESULTS.md` file.
- Publish your learning through the fork.
- Commit your changes and push to your forked repository.
- Share your work with others by creating a pull request.
- Your fork later serve as
    - Evidence of hands-on AI experience
    - A portfolio artifact
    - A reference for future projects












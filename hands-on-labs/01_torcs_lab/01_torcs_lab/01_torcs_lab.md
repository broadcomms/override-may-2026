***

# Learn to Design, Build, and Improve an Autonomous AI Driver with TORCS

## Overview

In this lab, you will work hands‑on with **TORCS (The Open Racing Car Simulator)** to understand how an autonomous AI driver works and how small changes to control logic can significantly affect performance. You will start with a **baseline AI driver**, observe its behavior on a race track, then modify and tune the driver to improve stability and speed.

This lab is designed as a **learning‑by‑doing experience**. There is no single “correct” solution — your goal is to **experiment, observe, and iterate**, just like real AI engineers do when working with simulations.

You are encouraged to fork this repository and publish your results. Your fork becomes part of your learning portfolio.

***

## Learning objectives

By completing this lab, you will learn how to:

*   Run an autonomous AI driver inside a racing simulator
*   Understand how sensor data is used to control steering, throttle, and braking
*   Modify Python code that controls a simulated vehicle
*   Experiment with parameters to balance speed and stability
*   Evaluate AI behavior qualitatively (what you see) and quantitatively (lap behavior)
*   Document and share your results on GitHub

***

## Lab structure

This lab is organized into incremental tasks:

*   **Task 1:** Run the baseline AI driver
*   **Task 2:** Understand how the driver controls the car
*   **Task 3:** Make your first modifications
*   **Task 4:** Experiment and optimize (optional, exploratory)
*   **Task 5:** Record results and reflect

Tasks marked as **Optional** provide less guidance and are designed to encourage deeper exploration.

***

## Before you begin

You will need a working TORCS environment.

Choose **one** of the following paths:

*   **Recommended:** Use the provided TORCS container (see `02_setup_guides/02.2_torcs_container_setup_guide.pdf`)
*   **Alternative:** Native Windows setup (see `02_setup_guides/02.1_torcs_windows_setup_guide.pdf`)

If TORCS is running and you can see the simulator window, you are ready to continue.

> **Tip:** Setup is intentionally separated from this lab. If something does not work, refer to the setup guides rather than trying to debug everything inside the lab steps.

***

## Task 1: Run the baseline AI driver

In this task, you will run the provided baseline AI driver without making any changes. The goal is simply to confirm that everything works and to observe how the car behaves.

### Step 1: Locate the driver code

Inside the files you downloaded, navigate to:

    gym_torcs/

The key file you will work with is:

    torcs_jm_par.py

This Python script:

*   Connects to TORCS over a network socket
*   Receives sensor data from the simulator
*   Sends steering, throttle, brake, and gear commands back to TORCS

You do **not** need to understand every line yet.

***

### Step 2: Start TORCS

1.  Launch TORCS.
2.  Navigate to:
    *   **Race → Practice**
    *   Configure the race so that **scr\_server** is selected as the driver.
3.  Start a new race.

You should see a **blue waiting screen** in TORCS. This is expected — TORCS is waiting for the AI agent to connect.

***

### Step 3: Run the baseline agent

From a terminal or command prompt:

```bash
python torcs_jm_par.py
```

If everything is working:

*   The terminal will show a successful connection message
*   The car will begin driving on the track automatically

✅ **Success criteria for Task 1**

*   The car moves on the track without human input
*   The simulation continues without crashing

Do not worry if:

*   The car is slow
*   The car occasionally goes off track
*   The driving looks “robotic”

That is normal — and expected.

***

## Task 2: Understand how the AI driver works

Now that the baseline driver is running, let’s understand **at a high level** how it controls the car.

### The control loop (conceptual)

Each simulation step follows this pattern:

1.  TORCS sends sensor data to the Python agent  
    Examples:
    *   Speed
    *   Angle to the track
    *   Distance from the center of the track

2.  The Python code decides:
    *   How much to steer
    *   Whether to accelerate or brake
    *   When to change gears

3.  The agent sends commands back to TORCS

This loop happens many times per second.

***

### Where decisions are made

Open `torcs_jm_par.py` and scroll until you find a section labeled something like:

    USER CONFIGURABLE PARAMETERS

You should see parameters similar to:

```python
TARGET_SPEED = 100
STEER_GAIN = 30
CENTERING_GAIN = 0.20
BRAKE_THRESHOLD = 0.9
ENABLE_TRACTION_CONTROL = True
```

These parameters strongly influence how the car behaves.

You are not training a neural network in this lab — instead, you are working with **rule‑based AI control**, which is a powerful way to learn the fundamentals of autonomy.

***

## Task 3: Make your first modification

In this task, you will make a **single, simple change** and observe its effect.

### Step 1: Increase the target speed

Locate the line:

```python
TARGET_SPEED = 100
```

Change it to:

```python
TARGET_SPEED = 150
```

Save the file.

***

### Step 2: Run the agent again

Make sure TORCS is still running and waiting for a connection, then run:

```bash
python torcs_jm_par.py
```

Watch the car carefully.

### What to observe

*   Does the car move faster on straight sections?
*   Does it struggle more in corners?
*   Does it go off track more often?

There is no “good” or “bad” result here — only observations.

✅ **Success criteria for Task 3**

*   You changed at least one parameter
*   You observed a visible change in driving behavior

***

## Task 4: Experiment and optimize (Optional)

This task is intentionally more open‑ended.

Try experimenting with **one parameter at a time**, for example:

*   Reduce `TARGET_SPEED` but increase `STEER_GAIN`
*   Lower `BRAKE_THRESHOLD` to brake earlier
*   Disable traction control and observe the effect

Example:

```python
STEER_GAIN = 25
BRAKE_THRESHOLD = 0.6
ENABLE_TRACTION_CONTROL = False
```

After each change:

1.  Save the file
2.  Restart the agent
3.  Observe the car

> **Tip:** The fastest car is not always the best learning outcome. Stability, control, and understanding matter more than lap time.

***

## Task 5: Record your results and reflect

Learning is most powerful when you reflect on what happened.

Open the file:

    RESULTS.md

Update it with:

*   What parameters you changed
*   What effect you observed
*   One thing that surprised you
*   One thing you would try next

This file becomes part of your **public learning artifact** when you publish your fork.

✅ **Success criteria for Task 5**

*   `RESULTS.md` is updated in your forked repository

***

## Summary

In this lab, you learned how to:

*   Run an autonomous AI driver in TORCS
*   Understand how sensor data influences control decisions
*   Modify AI behavior through Python parameters
*   Experiment safely inside a simulation
*   Document your learning on GitHub

This lab focused on **understanding and experimentation**, not competitions or leaderboards.

***

## Next steps

You can now:

*   Share your fork and results
*   Explore the **TORCS Customising Guide** to personalize cars and tracks
*   Try running TORCS in a container you build yourself
*   Apply these ideas to other autonomous or simulation‑based AI problems

Welcome to AI‑assisted, simulation‑driven development — and happy racing 🚗💨

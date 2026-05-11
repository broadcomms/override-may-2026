Copy this resutls file and paste it into your own repo to showcase your results! Lab results do not count towards your score you'll receive for your submission, but we encourage you to show off what you learned in the lab!
# Add your experiment results and reflections here
---

## IBM SkillsBuild TORCS Autonomous Driving Learning Lab. (May 2026)

**Objectives**
- Run an autonomous AI driver in a simulation environment (TORCS).
- Understand how sensor data is used to control
    - Steering
    - Throttle
    - Braking
- Modify Python code that controls a simulated vehicle.
- Use AI driver to understand how autonomous systems sense their 
    - environment,
    - make decisions, and 
    - act in real time.
- Experiment with control parameters and observe real-time effects.
- Learn how simulation is used in real-world AI development.
- Document and share your learning through GitHub repository.


### TORCS (The Open Racing Car Simulator)
- Safe, controled virtual environment for AI development.
- Test ideas safely
- Run experiments quickly
- Observe edge cases without real-world risks
- Iterate on models and logic before deployment.

**Features**
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

**Repository Structure**
Fork first, hands-on learning.
```sh
hands-on-lab/
└── README.md                # Read about the challenge labs ✅
└── 01_torcs_lab/
    ├── README_LAB.md        # Lab-specific overview 
    ├── 00_intro             # Conceptual introduction ✅
    ├── 01_torcs_lab.md      # Step-by-step learning lab ->TASKS
    ├── 02_setup_guides/     # Setup and reference guides ✅
    ├── 03_build_your_own_container/ # Advanced path (optional)
    ├── 04_files/            # TORCS and driver files
    └── RESULTS.md           # Results and reflections (you are here)
```
Work is inside `https://github.com/broadcomms/hands-on-lab/01_torcs_lab`
- AI driver code is in `/04_files/` directory.
- Results, notes and reflections are all here `RESULTS.md` file.

---

## 🏁 TORCS Lab (May Challenge)

- Start with a baseline AI driver
- Observe its behaviour on race track
- Modify and tune the driver to improve stability and speed.

Goal: "Experiment, observe and interate"

**Lab Structure**
- Task 1: Run the baseline AI driver
- Task 2: Understand how the driver controls the car
- Task 3: Make your first modifications
- Task 4: Experiment and optimize (optional, exploratory)
- Task 5: Record results and reflect

### Setup Guide
See `02_setup_guides/02.2_torcs_container_setup_guide.pdf`
-  Run container on Podman or docker desktop.
- `gym_torcs` python code that lets AI talk to TORCS
- SRC/port 3001 connection betweeen AI and TORCS
- VS Code, Granite AI


**System Resources**
- Linux Ubuntu 24.04 (WSL)
- 16 GB RAM, 30 GB diskpace
- 64-bit processor
- Chrome browser.
- Command Line Interface (CLI)

**Installation**
```sh
# Run in Windows PowerShell to open Linux CLI
wsl 

# Detect your architecture
uname -m # if x86_64 use amd64 image, else if aarch64 use arm64 image

# Clone the challenge hands on lab
cd ~
git clone https://github.com/broadcomms/hands-on-labs.git 
```

**Prepare YOur Workspace folder**
```sh
# Create workspace folder and check into it
mkdir -p ~/RaceYourCode
cd ~/RaceYourCode
# Copy and unzip the gym_torcs library into the workspace
unzip ~/hands-on-labs/01_torcs_lab/04_files/gym_torcs.zip
# Verify files are in the folder
ls gym_torcs -ltr  

# Output should list:
# - torcs_jm_par.py <- we are going to edit this.

# - snakeoil3_gym.py
# - gym_torcs.py
# - practice.xml

# NOTE: 
# Everything in RaceYourCode is visible inside container.
# /home/student/workspace (Works is synced betwen both folders)
# Work is never lost. Even after container is distroyed
```

**Pull and run the container**
```sh
docker run -it --rm \
  -p 5900:5900 -p 6080:6080 -p 3001:3001/udp \
  -v ~/RaceYourCode:/home/student/workspace \
  --name torcs docker.io/johnsloe/torcs-competition:amd64

# This should take about 10-15 minutes.
# When Installing Inside VS Code CLI, 
# if it get stucked VS Code install-extension 
# [0/6] Checking persistent home directory...
# [1/6] Checking VS Code extensions...
# Check if code is still running
docker exec torcs ps -ef | grep -E "code|node"
# if you see `code` process that is what is blocking
# Kill the process and the installation will continue
docker exec torcs pkill -f "code.*install-extension"
# Check the logs
docker logs torcs --tail 50
# Or in another Terminal follow `docker logs -f torcs`
# You shound see proxying from :6080 to localhost:5900
```
Output:
```
 Environment ready!

 Desktop (browser) : http://localhost:6080/vnc.html
 Desktop (VNC)     : localhost:5900
 Ollama API        : http://localhost:11434
 TORCS SCR port    : 3001 (UDP)
 Student workspace : /home/student/workspace
 ```



**Open the Browser Desktop** 
http://localhost:6080/vnc.html

Click `Connect` to land on the XFCE desktop.

From there Right-click → `Open Terminal Here`

Fix Ollama Bug in container
```sh
# Check what errored in the logs
cat /tmp/ollama.log
# From WSL terminal make student owner of ollama directory
docker exec -u root torcs chown -R student:student /opt/ollama
docker exec -u root torcs chown -R student:student /tmp
# Create system wide marker from WSL terminal for VS Code
docker exec -u root torcs bash -c 'echo "DONT_PROMPT_WSL_INSTALL=1" >> /etc/environment'
# Back in the Container terminal
ollama serve > /tmp/ollama.log 2>&1 &
sleep 5
ollama list
# If you dont see granite4:350m
# Pull granite
ollama pull granite4:350m 
# After Success verify granite is install
ollama list
# Test inference to ensure it is running from CLI
ollama run granite4:350m "Say hello in one short sentence."
# Test the ollama HTTP API
curl http://localhost:11434/api/generate -d '{
  "model": "granite4:350m",
  "prompt": "What is 2+2?",
  "stream": false
}'
```

```sh
# Add this to shell to silent VS Code permission
echo 'export DONT_PROMPT_WSL_INSTALL=1' >> ~/.bashrc
echo 'export DONT_PROMPT_WSL_INSTALL=1' >> ~/.profile
source ~/.bashrc
# Test it inside of VS Code inside the container
code /home/student/workspace/gym_torcs
# If above doesnt work, run it verbatim
code --no-sandbox --verbose /home/student/workspace/gym_torcs 2>&1 | head -40
# NOTE:
# Changes saved in vscode will be saved instantly on both bindings.
```






**Reset the code**
```sh
# stop and remove the torcs container
docker stop torcs 2>/dev/null
docker rm torcs 2>/dev/null
# keep the image and clean just Your Code (save 10GB download)
# docker rmi docker.io/johnsloe/torcs-competition:amd64
rm -rf ~/RaceYourCode
mkdir -p ~/RaceYourCode
cd ~/RaceYourCode
unzip ~/hands-on-labs/01_torcs_lab/04_files/gym_torcs.zip
# Verify `torcs` container is no more running
docker ps
# Start back afresh
docker run -it --rm \
  -p 5900:5900 -p 6080:6080 -p 3001:3001/udp \
  -v ~/RaceYourCode:/home/student/workspace \
  --name torcs docker.io/johnsloe/torcs-competition:amd64

# In another terminal
docker logs -f torcs
# If you see it stucked at code extension install run this
docker exec torcs pkill -f "code.*install-extension"

```






## PODMAN INSTALL ON WSL

```sh
# Connect to WSL
wsl
# Install podman
sudo apt-get update && sudo apt-get -y install podman
# Pull and start the container
podman run -it --rm -p 5900:5900 -p 6080:6080 -p 3001:3001/udp -v ~/RaceYourCode:/home/student/workspace:Z --name torcs docker.io/johnsloe/torcs-competition:amd64

podman logs -f torcs
podman exec torcs pkill -f "code.*install-extension"
podman exec -u root torcs bash -c 'echo "DONT_PROMPT_WSL_INSTALL=1" >> /etc/environment'

podman exec -u root torcs chown -R student:student /opt/ollama
podman exec -u root torcs chown -R student:student /tmp

# Connect http://localhost:6080/vnc.html
# Right Click -> Open New Terminal
ollama serve
# On same terminal window -> File -> Open Tab
ollama list
ollama list
# If you dont see granite4:350m
# Pull granite
ollama pull granite4:350m 
# After Success verify granite is install
ollama list
# Test inference to ensure it is running from CLI
ollama run granite4:350m "Say hello in one short sentence."
# Test the ollama HTTP API
curl http://localhost:11434/api/generate -d '{
  "model": "granite4:350m",
  "prompt": "What is 2+2?",
  "stream": false
}'
```


**Start TORCS from the terminal**
Follow section 6 to 7 of the [Container guide](02_setup_guides/02.2_torcs_container_setup_guide.pdf) 

```sh
# Start TORCS
torcs &
```
Navigate Inside TORCS main menu:
> Race → Practice → Configure Race → pick a track → Accept  → set driver to `scr_server` → Accept → Accept.

Back to the Pactice Menu
> New Race

```sh
# Open second terminal and run
cd /home/student/workspace/gym_torcs
ls
# You should see torcs_jm_par.py, snakeoil3_gym.py, gym_torcs.py, and others

# Execute to start the car drving
python3 torcs_jm_par.py

# Stop the agent
Ctrl + c

# Quit TORCS by pressing ESC, then selecting Quit.
# Then in the terminal from where you started TORCS
Ctrl + c
```

**Using VS Code and the AI Coding Assistant**
```sh
# From a terminal inside the container run
code /home/student/workspace/gym_torcs 

# Install Continue.dev now and Python extension if not available
# - Extensions -> Continue - open-source AI code agent (By Continue)
# - Extensions -> Python (By Microssoft)



# Click on the Continue Icon to open the chat assistant.
# Type a question and see granite explain your code for you
# Question: "What does the STEER_GAIN parameter do in this file? "

```

**Making Changes to the AI**

```sh 
# Click on torcs_jm_par.py to open it
# Scroll to the section labelled USER CONFIGURABLE PARAMETERS (around line 493).
# You should see
TARGET_SPEED = 100      
# Target speed in km/h 
STEER_GAIN = 30         
# Steering sensitivity 
CENTERING_GAIN = 0.20   # How strongly car stays centred 
BRAKE_THRESHOLD = 0.9   # When to brake in corners 
GEAR_SPEEDS = [0, 20, 40, 80, 100, 180]  # Gear shift points 
ENABLE_TRACTION_CONTROL = True 


# Change Target Speed
TARGET_SPEED = 150 

# Load TORCS then

```






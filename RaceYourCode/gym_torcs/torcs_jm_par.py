
import socket
import sys
import getopt
import os
import time
import json
import time as _time  # alias avoids shadowing if local `time` var used elsewhere
PI= 3.14159265359

data_size = 2**17
DEFAULT_MAX_STEPS = 100000
STEPS_PER_LAP_BUDGET = 8000

ophelp=  'Options:\n'
ophelp+= ' --host, -H <host>    TORCS server host. [localhost]\n'
ophelp+= ' --port, -p <port>    TORCS port. [3001]\n'
ophelp+= ' --id, -i <id>        ID for server. [SCR]\n'
ophelp+= ' --steps, -m <#>      Maximum simulation steps. 1 sec ~ 50 steps. [100000]\n'
ophelp+= ' --episodes, -e <#>   Maximum learning episodes. [1]\n'
ophelp+= ' --track, -t <track>  Your name for this track. Used for learning. [unknown]\n'
ophelp+= ' --stage, -s <#>      0=warm up, 1=qualifying, 2=race, 3=unknown. [3]\n'
ophelp+= ' --debug, -d          Output full telemetry.\n'
ophelp+= ' --help, -h           Show this help.\n'
ophelp+= ' --version, -v        Show current version.'
usage= 'Usage: %s [ophelp [optargs]] \n' % sys.argv[0]
usage= usage + ophelp
version= "20130505-2"

def clip(v,lo,hi):
    if v<lo: return lo
    elif v>hi: return hi
    else: return v

def bargraph(x,mn,mx,w,c='X'):
    '''Draws a simple asciiart bar graph. Very handy for
    visualizing what's going on with the data.
    x= Value from sensor, mn= minimum plottable value,
    mx= maximum plottable value, w= width of plot in chars,
    c= the character to plot with.'''
    if not w: return '' # No width!
    if x<mn: x= mn      # Clip to bounds.
    if x>mx: x= mx      # Clip to bounds.
    tx= mx-mn # Total real units possible to show on graph.
    if tx<=0: return 'backwards' # Stupid bounds.
    upw= tx/float(w) # X Units per output char width.
    if upw<=0: return 'what?' # Don't let this happen.
    negpu, pospu, negnonpu, posnonpu= 0,0,0,0
    if mn < 0: # Then there is a negative part to graph.
        if x < 0: # And the plot is on the negative side.
            negpu= -x + min(0,mx)
            negnonpu= -mn + x
        else: # Plot is on pos. Neg side is empty.
            negnonpu= -mn + min(0,mx) # But still show some empty neg.
    if mx > 0: # There is a positive part to the graph
        if x > 0: # And the plot is on the positive side.
            pospu= x - max(0,mn)
            posnonpu= mx - x
        else: # Plot is on neg. Pos side is empty.
            posnonpu= mx - max(0,mn) # But still show some empty pos.
    nnc= int(negnonpu/upw)*'-'
    npc= int(negpu/upw)*c
    ppc= int(pospu/upw)*c
    pnc= int(posnonpu/upw)*'_'
    return '[%s]' % (nnc+npc+ppc+pnc)

class Client():
    def __init__(self,H=None,p=None,i=None,e=None,t=None,s=None,d=None,vision=False):
        self.vision = vision

        self.host= 'localhost'
        self.port= 3001
        self.sid= 'SCR'
        self.maxEpisodes=1 # "Maximum number of learning episodes to perform"
        self.trackname= 'unknown'
        self.stage= 3 # 0=Warm-up, 1=Qualifying 2=Race, 3=unknown <Default=3>
        self.debug= False
        self.maxSteps= DEFAULT_MAX_STEPS  # 50steps/second
        self.parse_the_command_line()
        if H: self.host= H
        if p: self.port= p
        if i: self.sid= i
        if e: self.maxEpisodes= e
        if t: self.trackname= t
        if s: self.stage= s
        if d: self.debug= d
        self.S= ServerState()
        self.R= DriverAction()
        self.setup_connection()

    def setup_connection(self):
        try:
            self.so= socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error as emsg:
            print('Error: Could not create socket...')
            sys.exit(-1)
        self.so.settimeout(1)

        n_fail = 5
        while True:
            a= "-45 -19 -12 -7 -4 -2.5 -1.7 -1 -.5 0 .5 1 1.7 2.5 4 7 12 19 45"

            initmsg='%s(init %s)' % (self.sid,a)

            try:
                self.so.sendto(initmsg.encode(), (self.host, self.port))
            except socket.error as emsg:
                sys.exit(-1)
            sockdata= str()
            try:
                sockdata,addr= self.so.recvfrom(data_size)
                sockdata = sockdata.decode('utf-8')
            except socket.error as emsg:
                print("Waiting for server on %d............" % self.port)
                print("Count Down : " + str(n_fail))
                if n_fail < 0:
                    print("relaunch torcs")
                    os.system('pkill torcs')
                    time.sleep(1.0)
                    if self.vision is False:
                        os.system('torcs -nofuel -nodamage -nolaptime &')
                    else:
                        os.system('torcs -nofuel -nodamage -nolaptime -vision &')

                    time.sleep(1.0)
                    os.system('sh autostart.sh')
                    n_fail = 5
                n_fail -= 1

            identify = '***identified***'
            if identify in sockdata:
                print("Client connected on %d.............." % self.port)
                break

    def parse_the_command_line(self):
        try:
            (opts, args) = getopt.getopt(sys.argv[1:], 'H:p:i:m:e:t:s:dhv',
                       ['host=','port=','id=','steps=',
                        'episodes=','track=','stage=',
                        'debug','help','version'])
        except getopt.error as why:
            print('getopt error: %s\n%s' % (why, usage))
            sys.exit(-1)
        try:
            for opt in opts:
                if opt[0] == '-h' or opt[0] == '--help':
                    print(usage)
                    sys.exit(0)
                if opt[0] == '-d' or opt[0] == '--debug':
                    self.debug= True
                if opt[0] == '-H' or opt[0] == '--host':
                    self.host= opt[1]
                if opt[0] == '-i' or opt[0] == '--id':
                    self.sid= opt[1]
                if opt[0] == '-t' or opt[0] == '--track':
                    self.trackname= opt[1]
                if opt[0] == '-s' or opt[0] == '--stage':
                    self.stage= int(opt[1])
                if opt[0] == '-p' or opt[0] == '--port':
                    self.port= int(opt[1])
                if opt[0] == '-e' or opt[0] == '--episodes':
                    self.maxEpisodes= int(opt[1])
                if opt[0] == '-m' or opt[0] == '--steps':
                    self.maxSteps= int(opt[1])
                if opt[0] == '-v' or opt[0] == '--version':
                    print('%s %s' % (sys.argv[0], version))
                    sys.exit(0)
        except ValueError as why:
            print('Bad parameter \'%s\' for option %s: %s\n%s' % (
                                       opt[1], opt[0], why, usage))
            sys.exit(-1)
        if len(args) > 0:
            print('Superflous input? %s\n%s' % (', '.join(args), usage))
            sys.exit(-1)

    def get_servers_input(self):
        '''Server's input is stored in a ServerState object'''
        if not self.so: return
        sockdata= str()

        while True:
            try:
                sockdata,addr= self.so.recvfrom(data_size)
                sockdata = sockdata.decode('utf-8')
            except socket.error as emsg:
                print('.', end=' ')
            if '***identified***' in sockdata:
                print("Client connected on %d.............." % self.port)
                continue
            elif '***shutdown***' in sockdata:
                print((("Server has stopped the race on %d. "+
                        "You were in %d place.") %
                        (self.port,self.S.d['racePos'])))
                self.shutdown()
                return
            elif '***restart***' in sockdata:
                print("Server has restarted the race on %d." % self.port)
                self.shutdown()
                return
            elif not sockdata: # Empty?
                continue       # Try again.
            else:
                self.S.parse_server_str(sockdata)
                if self.debug:
                    sys.stderr.write("\x1b[2J\x1b[H") # Clear for steady output.
                    print(self.S)
                break # Can now return from this function.

    def respond_to_server(self):
        if not self.so: return
        try:
            message = repr(self.R)
            self.so.sendto(message.encode(), (self.host, self.port))
        except socket.error as emsg:
            print("Error sending to server: %s Message %s" % (emsg[1],str(emsg[0])))
            sys.exit(-1)
        if self.debug: print(self.R.fancyout())

    def shutdown(self):
        if not self.so: return
        print(("Race terminated or %d steps elapsed. Shutting down %d."
               % (self.maxSteps,self.port)))
        self.so.close()
        self.so = None

class ServerState():
    '''What the server is reporting right now.'''
    def __init__(self):
        self.servstr= str()
        self.d= dict()

    def parse_server_str(self, server_string):
        '''Parse the server string.'''
        self.servstr= server_string.strip()[:-1]
        sslisted= self.servstr.strip().lstrip('(').rstrip(')').split(')(')
        for i in sslisted:
            w= i.split(' ')
            self.d[w[0]]= destringify(w[1:])
        # OVERRIDE telemetry logger lives in the main loop (after drive_modular)
        # so the JSONL captures both the server-sensor state (self.d here)
        # AND the driver's accel/brake/steer/gear commands (in C.R.d). At this
        # point in parse_server_str, R hasn't been computed for this tick yet
        # — task 1.5 first attempt logged self.d only and got harvest/deploy=0
        # because brake/accel keys live in R, not S. See the __main__ block.

    def __repr__(self):
        return self.fancyout()
        out= str()
        for k in sorted(self.d):
            strout= str(self.d[k])
            if type(self.d[k]) is list:
                strlist= [str(i) for i in self.d[k]]
                strout= ', '.join(strlist)
            out+= "%s: %s\n" % (k,strout)
        return out

    def fancyout(self):
        '''Specialty output for useful ServerState monitoring.'''
        out= str()
        sensors= [ # Select the ones you want in the order you want them.
        'stucktimer',
        'fuel',
        'distRaced',
        'distFromStart',
        'opponents',
        'wheelSpinVel',
        'z',
        'speedZ',
        'speedY',
        'speedX',
        'targetSpeed',
        'rpm',
        'skid',
        'slip',
        'track',
        'trackPos',
        'angle',
        ]

        for k in sensors:
            if type(self.d.get(k)) is list: # Handle list type data.
                if k == 'track': # Nice display for track sensors.
                    strout= str()
                    raw_tsens= ['%.1f'%x for x in self.d['track']]
                    strout+= ' '.join(raw_tsens[:9])+'_'+raw_tsens[9]+'_'+' '.join(raw_tsens[10:])
                elif k == 'opponents': # Nice display for opponent sensors.
                    strout= str()
                    for osensor in self.d['opponents']:
                        if   osensor >190: oc= '_'
                        elif osensor > 90: oc= '.'
                        elif osensor > 39: oc= chr(int(osensor/2)+97-19)
                        elif osensor > 13: oc= chr(int(osensor)+65-13)
                        elif osensor >  3: oc= chr(int(osensor)+48-3)
                        else: oc= '?'
                        strout+= oc
                    strout= ' -> '+strout[:18] + ' ' + strout[18:]+' <-'
                else:
                    strlist= [str(i) for i in self.d[k]]
                    strout= ', '.join(strlist)
            else: # Not a list type of value.
                if k == 'gear': # This is redundant now since it's part of RPM.
                    gs= '_._._._._._._._._'
                    p= int(self.d['gear']) * 2 + 2  # Position
                    l= '%d'%self.d['gear'] # Label
                    if l=='-1': l= 'R'
                    if l=='0':  l= 'N'
                    strout= gs[:p]+ '(%s)'%l + gs[p+3:]
                elif k == 'damage':
                    strout= '%6.0f %s' % (self.d[k], bargraph(self.d[k],0,10000,50,'~'))
                elif k == 'fuel':
                    strout= '%6.0f %s' % (self.d[k], bargraph(self.d[k],0,100,50,'f'))
                elif k == 'speedX':
                    cx= 'X'
                    if self.d[k]<0: cx= 'R'
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k],-30,300,50,cx))
                elif k == 'speedY': # This gets reversed for display to make sense.
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k]*-1,-25,25,50,'Y'))
                elif k == 'speedZ':
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k],-13,13,50,'Z'))
                elif k == 'z':
                    strout= '%6.3f %s' % (self.d[k], bargraph(self.d[k],.3,.5,50,'z'))
                elif k == 'trackPos': # This gets reversed for display to make sense.
                    cx='<'
                    if self.d[k]<0: cx= '>'
                    strout= '%6.3f %s' % (self.d[k], bargraph(self.d[k]*-1,-1,1,50,cx))
                elif k == 'stucktimer':
                    if self.d[k]:
                        strout= '%3d %s' % (self.d[k], bargraph(self.d[k],0,300,50,"'"))
                    else: strout= 'Not stuck!'
                elif k == 'rpm':
                    g= self.d['gear']
                    if g < 0:
                        g= 'R'
                    else:
                        g= '%1d'% g
                    strout= bargraph(self.d[k],0,10000,50,g)
                elif k == 'angle':
                    asyms= [
                          "  !  ", ".|'  ", "./'  ", "_.-  ", ".--  ", "..-  ",
                          "---  ", ".__  ", "-._  ", "'-.  ", r"'\.  ", "'|.  ",
                          "  |  ", "  .|'", "  ./'", "  .-'", "  _.-", "  __.",
                          "  ---", "  --.", "  -._", "  -..", r"  '\.", "  '|."  ]
                    rad= self.d[k]
                    deg= int(rad*180/PI)
                    symno= int(.5+ (rad+PI) / (PI/12) )
                    symno= symno % (len(asyms)-1)
                    strout= '%5.2f %3d (%s)' % (rad,deg,asyms[symno])
                elif k == 'skid': # A sensible interpretation of wheel spin.
                    frontwheelradpersec= self.d['wheelSpinVel'][0]
                    skid= 0
                    if frontwheelradpersec:
                        skid= .5555555555*self.d['speedX']/frontwheelradpersec - .66124
                    strout= bargraph(skid,-.05,.4,50,'*')
                elif k == 'slip': # A sensible interpretation of wheel spin.
                    frontwheelradpersec= self.d['wheelSpinVel'][0]
                    slip= 0
                    if frontwheelradpersec:
                        slip= ((self.d['wheelSpinVel'][2]+self.d['wheelSpinVel'][3]) -
                              (self.d['wheelSpinVel'][0]+self.d['wheelSpinVel'][1]))
                    strout= bargraph(slip,-5,150,50,'@')
                else:
                    strout= str(self.d[k])
            out+= "%s: %s\n" % (k,strout)
        return out

class DriverAction():
    '''What the driver is intending to do (i.e. send to the server).
    Composes something like this for the server:
    (accel 1)(brake 0)(gear 1)(steer 0)(clutch 0)(focus 0)(meta 0) or
    (accel 1)(brake 0)(gear 1)(steer 0)(clutch 0)(focus -90 -45 0 45 90)(meta 0)'''
    def __init__(self):
       self.actionstr= str()
       self.d= { 'accel':0.2,
                   'brake':0,
                  'clutch':0,
                    'gear':1,
                   'steer':0,
                   'focus':[-90,-45,0,45,90],
                    'meta':0
                    }

    def clip_to_limits(self):
        """There pretty much is never a reason to send the server
        something like (steer 9483.323). This comes up all the time
        and it's probably just more sensible to always clip it than to
        worry about when to. The "clip" command is still a snakeoil
        utility function, but it should be used only for non standard
        things or non obvious limits (limit the steering to the left,
        for example). For normal limits, simply don't worry about it."""
        self.d['steer']= clip(self.d['steer'], -1, 1)
        self.d['brake']= clip(self.d['brake'], 0, 1)
        self.d['accel']= clip(self.d['accel'], 0, 1)
        self.d['clutch']= clip(self.d['clutch'], 0, 1)
        if self.d['gear'] not in [-1, 0, 1, 2, 3, 4, 5, 6]:
            self.d['gear']= 0
        if self.d['meta'] not in [0,1]:
            self.d['meta']= 0
        if type(self.d['focus']) is not list or min(self.d['focus'])<-180 or max(self.d['focus'])>180:
            self.d['focus']= 0

    def __repr__(self):
        self.clip_to_limits()
        out= str()
        for k in self.d:
            out+= '('+k+' '
            v= self.d[k]
            if not type(v) is list:
                out+= '%.3f' % v
            else:
                out+= ' '.join([str(x) for x in v])
            out+= ')'
        return out
        return out+'\n'

    def fancyout(self):
        '''Specialty output for useful monitoring of bot's effectors.'''
        out= str()
        od= self.d.copy()
        od.pop('gear','') # Not interesting.
        od.pop('meta','') # Not interesting.
        od.pop('focus','') # Not interesting. Yet.
        for k in sorted(od):
            if k == 'clutch' or k == 'brake' or k == 'accel':
                strout=''
                strout= '%6.3f %s' % (od[k], bargraph(od[k],0,1,50,k[0].upper()))
            elif k == 'steer': # Reverse the graph to make sense.
                strout= '%6.3f %s' % (od[k], bargraph(od[k]*-1,-1,1,50,'S'))
            else:
                strout= str(od[k])
            out+= "%s: %s\n" % (k,strout)
        return out

def destringify(s):
    '''makes a string into a value or a list of strings into a list of
    values (if possible)'''
    if not s: return s
    if type(s) is str:
        try:
            return float(s)
        except ValueError:
            print("Could not find a value in %s" % s)
            return s
    elif type(s) is list:
        if len(s) < 2:
            return destringify(s[0])
        else:
            return [destringify(i) for i in s]

def drive_example(c):
    '''This is only an example. It will get around the track but the
    correct thing to do is write your own `drive()` function.'''
    S,R= c.S.d,c.R.d
    target_speed=40

    R['steer']= S['angle']*25 / PI
    R['steer']-= S['trackPos']*.25

    R['accel'] = max(0.0, min(1.0, R['accel']))
    

    if S['speedX'] < target_speed - (R['steer']*2.5):
        R['accel']+= .4
    else:
        R['accel']-= .2
    if S['speedX']<10:
       R['accel']+= 1/(S['speedX']+.1)

    if ((S['wheelSpinVel'][2]+S['wheelSpinVel'][3]) -
       (S['wheelSpinVel'][0]+S['wheelSpinVel'][1]) > 2):
       R['accel']-= 0.1



    R['gear']=1
    if S['speedX']>60:
        R['gear']=2
    if S['speedX']>100:
        R['gear']=3
    if S['speedX']>140:
        R['gear']=4
    if S['speedX']>190:
        R['gear']=5
    if S['speedX']>220:
        R['gear']=6
    return

# (Reference function only — the active driver is `drive_modular` below,
# wired into the runtime via the single __main__ block at the bottom.
# Original file had an earlier `if __name__ == "__main__":` block here
# that called drive_example with a hard-coded target_speed=40, which ran
# to maxSteps exhaustion before the modular main block could ever fire —
# effectively dead-coding the USER CONFIGURABLE PARAMETERS section. The
# legacy main block was removed so TARGET_SPEED below takes effect.)


#############################################
# MODULAR DRIVE LOGIC WITH USER PARAMETERS  #
#############################################

import math

# ================= USER CONFIGURABLE PARAMETERS =================
TARGET_SPEED = 85  # Safe straight-line cap for the branded demo path.
MIN_TARGET_SPEED = 35
STEER_GAIN = 22
CENTERING_GAIN = 0.35
TRACK_SENSOR_GAIN = 0.60
BRAKE_THRESHOLD = 0.55  # Angle threshold for braking. Lower values brake earlier.
GEAR_SPEEDS = [0, 20, 40, 80, 100, 180]  # Speed thresholds for gear shifting.
ENABLE_TRACTION_CONTROL = True  # Toggle traction control system.
OFFTRACK_TRACKPOS = 0.85
OFFTRACK_ANGLE = 0.60
RECOVERY_SPEED_KMH = 25
LAUNCH_GUARD_S = 15

# ================= HELPER FUNCTIONS =================
def _track_triplet(S):
    track = S.get('track')
    if not isinstance(track, list) or len(track) < 11:
        return None
    left = float(track[8] or 0.0)
    centre = max(float(track[9] or 0.0), 1.0)
    right = float(track[10] or 0.0)
    return left, centre, right


def calculate_target_speed(S):
    triplet = _track_triplet(S)
    if triplet is None:
        return TARGET_SPEED

    left, centre, right = triplet
    visible_road = min(left, centre, right)
    curvature = abs(left - right)

    target = MIN_TARGET_SPEED + min(centre, 120.0) * 0.45
    target -= min(curvature, 80.0) * 0.30
    target -= max(0.0, 20.0 - visible_road) * 0.50
    return clip(target, MIN_TARGET_SPEED, TARGET_SPEED)


def calculate_steering(S):
    steer = (S['angle'] * STEER_GAIN / math.pi) - (S['trackPos'] * CENTERING_GAIN)
    triplet = _track_triplet(S)
    if triplet is not None:
        left, centre, right = triplet
        steer += ((left - right) / centre) * TRACK_SENSOR_GAIN
    return max(-1, min(1, steer))

def calculate_throttle(S, R, target_speed):
    speed = float(S.get('speedX', 0.0) or 0.0)
    steer = float(R.get('steer', 0.0) or 0.0)
    accel_now = float(R.get('accel', 0.0) or 0.0)

    if speed < target_speed - (abs(steer) * 8.0):
        accel = min(1.0, accel_now + 0.4)
    else:
        accel = max(0.0, accel_now - 0.2)

    # Guard against the launch/back-roll trap: the original Gym-TORCS
    # expression used `1 / (speedX + 0.1)`, which becomes sharply negative
    # as soon as the car drifts backward a little. That immediately zeroes
    # throttle, the car keeps rolling backward, and recovery never reaches
    # a stable forward launch.
    if speed < 10:
        accel += 1 / (max(speed, 0.0) + 0.1)
    return max(0.0, min(1.0, accel))

def apply_brakes(S, target_speed):
    speed = float(S.get('speedX', 0.0) or 0.0)
    angle = abs(float(S.get('angle', 0.0) or 0.0))
    track_pos = abs(float(S.get('trackPos', 0.0) or 0.0))

    if speed > target_speed + 12:
        return clip((speed - target_speed) / 35.0, 0.0, 0.7)
    if angle > BRAKE_THRESHOLD and speed > 45:
        return 0.3
    if track_pos > 0.6 and speed > 30:
        return 0.4
    return 0.0

def shift_gears(S):
    gear = 1
    for i, speed in enumerate(GEAR_SPEEDS):
        if S['speedX'] > speed:
            gear = i + 1
    return min(gear, 6)

def traction_control(S, accel):
    if ENABLE_TRACTION_CONTROL:
        if ((S['wheelSpinVel'][2] + S['wheelSpinVel'][3]) - (S['wheelSpinVel'][0] + S['wheelSpinVel'][1])) > 2:
            accel -= 0.1
    return max(0.0, accel)


def derive_max_steps(laps):
    try:
        lap_count = int(laps)
    except (TypeError, ValueError):
        lap_count = 0
    if lap_count <= 0:
        return DEFAULT_MAX_STEPS
    return max(DEFAULT_MAX_STEPS, lap_count * STEPS_PER_LAP_BUDGET)


def apply_launch_guard(S, R):
    """Keep the opening seconds biased toward a clean forward launch.

    In the failing cockpit_practice runs, TORCS was letting the car drift
    backward off the line before our simple throttle logic settled. Once
    speedX went slightly negative, the old low-speed boost would collapse
    throttle and the driver would spiral into recovery mode.

    For the first few seconds, if the car is still mostly aligned with the
    track and undamaged, prefer a straight-ahead forward push instead of
    aggressive steering or reverse recovery.
    """
    cur_lap_time = float(S.get('curLapTime', 0.0) or 0.0)
    speed = float(S.get('speedX', 0.0) or 0.0)
    track_pos = float(S.get('trackPos', 0.0) or 0.0)
    angle = float(S.get('angle', 0.0) or 0.0)
    damage = float(S.get('damage', 0.0) or 0.0)

    if cur_lap_time < 0 or cur_lap_time > LAUNCH_GUARD_S:
        return False
    if damage > 0:
        return False
    if speed >= 0:
        return False
    if abs(track_pos) > 0.5 or abs(angle) > 0.8:
        return False

    R['gear'] = 1
    R['accel'] = 1.0
    R['brake'] = 0.0
    R['steer'] = clip((-angle * 0.25) - (track_pos * 0.10), -0.35, 0.35)
    return True


def apply_recovery(S, R):
    """Recover from wall/off-track states before TORCS times out the client.

    The live probe showed the demo driver getting pinned near the wall with
    `trackPos ~= -0.95`, `angle ~= 0.76`, `speedX ~= 4`, `rpm = 0`, while still
    commanding full throttle + full steering lock. That leaves the server
    waiting on effectively non-progressing control updates and the race ends
    after a couple of laps.

    This branch trades pace for survival: brake hard when we're still rolling
    forward into trouble, then use reverse with steering toward the track
    centre once the car is nearly stopped or obviously stuck.
    """
    track_pos = float(S.get('trackPos', 0.0) or 0.0)
    angle = float(S.get('angle', 0.0) or 0.0)
    speed = float(S.get('speedX', 0.0) or 0.0)
    stuck = float(S.get('stucktimer', 0.0) or 0.0)
    damage = float(S.get('damage', 0.0) or 0.0)

    if apply_launch_guard(S, R):
        return True

    needs_recovery = (
        abs(track_pos) > OFFTRACK_TRACKPOS
        or (abs(angle) > OFFTRACK_ANGLE and speed < 20)
        or stuck > 20
        or damage > 0
    )
    if not needs_recovery:
        return False

    steer_back = clip((-angle * 0.8) - (track_pos * 0.8), -1, 1)
    if speed > RECOVERY_SPEED_KMH:
        R['gear'] = max(1, int(R.get('gear', 1)))
        R['accel'] = 0.0
        R['brake'] = 0.6
        R['steer'] = steer_back
        return True

    if damage > 0 and abs(speed) < 2:
        R['gear'] = -1
        R['accel'] = 0.2
        R['brake'] = 0.0
        R['steer'] = clip(angle + (track_pos * 0.35), -0.7, 0.7)
        return True

    if speed < -2 and damage <= 0:
        R['gear'] = 1
        R['accel'] = 0.8
        R['brake'] = 0.0
        R['steer'] = clip((-angle * 0.35) - (track_pos * 0.15), -0.5, 0.5)
        return True

    R['gear'] = 1
    R['accel'] = 0.2
    R['brake'] = 0.1
    R['steer'] = steer_back
    return True

# ================= MAIN DRIVE FUNCTION =================
def drive_modular(c):
    S, R = c.S.d, c.R.d
    target_speed = calculate_target_speed(S)
    R['steer'] = calculate_steering(S)
    R['accel'] = calculate_throttle(S, R, target_speed)
    R['brake'] = apply_brakes(S, target_speed)
    R['accel'] = traction_control(S, R['accel'])
    R['gear'] = shift_gears(S)
    if apply_recovery(S, R):
        return
    return

# ================= MAIN LOOP =================
if __name__ == "__main__":
    C = Client(p=3001)
    C.maxSteps = derive_max_steps(os.environ.get("OVERRIDE_LAPS"))
    # OVERRIDE telemetry logger — env-gated (set OVERRIDE_LOG_TELEMETRY to a
    # JSONL path). Per-tick observation merges server-sensor state (C.S.d)
    # with the just-computed driver action (C.R.d: accel/brake/steer/gear)
    # so ingest/torcs_parser.py can integrate brake-on and throttle-≥-0.95
    # time per sector. R is keyed at the top level (no nesting) so the
    # parser's existing dict.get("brake", ...) / dict.get("accel", ...)
    # lookups work without any change.
    # Phase 1 session-boundary fix: if OVERRIDE_LOG_TELEMETRY is set to a
    # directory (trailing slash OR existing dir), auto-generate a per-run
    # filename `run_{YYYYMMDDTHHMMSS}.jsonl` so each TORCS race produces a
    # distinct capture file. Literal paths still work (backward compat).
    _override_log = os.environ.get("OVERRIDE_LOG_TELEMETRY")
    _override_fh = None
    if _override_log:
        try:
            _log_is_dir = (
                _override_log.endswith("/")
                or _override_log.endswith(os.sep)
                or os.path.isdir(_override_log)
            )
            if _log_is_dir:
                _ts = _time.strftime("%Y%m%dT%H%M%S", _time.gmtime())
                os.makedirs(_override_log, exist_ok=True)
                _override_log = os.path.join(_override_log, f"run_{_ts}.jsonl")
            else:
                os.makedirs(os.path.dirname(_override_log) or ".", exist_ok=True)
            # Line-buffered (buffering=1) so the live-ingest endpoint sees
            # complete observations as they're written — eliminates the
            # "incomplete tail" symptom the parser's safe-read mitigates.
            _override_fh = open(_override_log, "a", buffering=1)
            sys.stderr.write(f"[override] telemetry → {_override_log}\n")
        except OSError as _e:
            sys.stderr.write(
                f"[override] WARNING: OVERRIDE_LOG_TELEMETRY={_override_log!r} "
                f"could not be opened: {_e}. Telemetry capture will be empty.\n"
            )
    try:
        for step in range(C.maxSteps, 0, -1):
            C.get_servers_input()
            if C.so is None:
                break
            drive_modular(C)
            if _override_fh is not None:
                try:
                    _override_fh.write(json.dumps({
                        "t": _time.time(),
                        **C.S.d,        # server sensors: angle, speedX, distFromStart, ...
                        **C.R.d,        # driver action: accel, brake, steer, gear
                    }, default=str) + "\n")
                except OSError as _e:
                    # Surface once, don't spam every tick.
                    if not getattr(C, "_override_log_warned", False):
                        sys.stderr.write(
                            f"[override] WARNING: telemetry write failed: {_e}\n"
                        )
                        C._override_log_warned = True
            C.respond_to_server()
        C.shutdown()
    finally:
        if _override_fh is not None:
            _override_fh.close()

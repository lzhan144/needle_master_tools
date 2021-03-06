# -*- coding: utf-8 -*-
"""
Created on Thu Oct 08 11:30:52 2015

@author: Chris Paxton
"""
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as Poly
from shapely.geometry import Polygon, Point # using to replace sympy
from matplotlib.collections import PatchCollection

from pdb import set_trace as woah

def safe_load_line(name,handle):
    l = handle.readline()[:-1].split(': ')
    assert(l[0] == name)

    return l[1].split(',')

def array_to_tuples(array):
    return zip(array[:,0],array[:,1])

# def check_intersect(a, b):
#     return a.poly.intersection(b.poly).area > 0.

class Environment:
    metadata = {'render.modes': ['rgb_array']}

    background_color = np.array([99., 153., 174.]) / 255

    def __init__(self, filename=None):

        self.t = 0
        self.height   = 0
        self.width    = 0
        self.needle   = None
        ''' TODO: how do we want to constrain the game time? '''
        self.max_time = 300
        ''' TODO keep track of which gate is next '''
        self.next_gate    = None
        self.filename = filename

        self.reset()

    def reset(self):
        ''' Create a new environment. Currently based on attached filename '''
        self.done = False
        self.ngates = 0
        self.gates = []
        self.surfaces = []
        self.t = 0
        # environment damage is the sum of the damage to all surfaces
        self.damage = 0
        self.passed_gates = 0
        self.next_gate = None

        if self.filename is not None:
            with open(self.filename, 'r') as file:
                self.load(file)

        self.needle = Needle(self.width, self.height)


    def render(self, mode='rgb_array', save_image=False):
        fig = plt.figure()
        plt.ylim(self.height)
        plt.xlim(self.width)
        frame = plt.gca()
        frame.set_facecolor(self.background_color)
        frame.axes.get_xaxis().set_ticks([])
        frame.axes.get_yaxis().set_ticks([])

        for surface in self.surfaces:
            surface.draw()

        for gate in self.gates:
            gate.draw()

        self.needle.draw()

        if save_image:
            frame.invert_xaxis()
            plt.savefig('{:03d}.png'.format(self.t))

        # Return the figure in a numpy buffer
        if mode == 'rgb_array':
            fig.canvas.draw()
            buf = fig.canvas.tostring_rgb()
            ncols, nrows = fig.canvas.get_width_height()
            plt.close('all')
            return np.fromstring(buf, dtype=np.uint8).reshape(nrows, ncols, 3)
        else:
            plt.close('all')

    @staticmethod
    def parse_name(filename):
        toks = filename.split('/')[-1].split('.')[0].split('_')
        return toks[1]

    '''
    Load an environment file.
    '''
    def load(self, handle):

        D = safe_load_line('Dimensions',handle)
        self.height = int(D[1])
        self.width = int(D[0])
        #print " - width=%d, height=%d"%(self.width, self.height)

        D = safe_load_line('Gates',handle)
        self.ngates = int(D[0])
        #print " - num gates=%d"%(self.ngates)

        for i in range(self.ngates):
            gate = Gate(self.width,self.height)
            gate.load(handle)
            self.gates.append(gate)

        if(self.ngates > 0):
            self.next_gate = 0
            self.gates[self.next_gate].status = 'next_gate'

        D = safe_load_line('Surfaces',handle)
        self.nsurfaces = int(D[0])
        #print " - num surfaces=%d"%(self.nsurfaces)

        for i in range(self.nsurfaces):
            s = Surface(self.width,self.height)
            s.load(handle)
            self.surfaces.append(s)

    def step(self, action):
        """
            Move one time step forward
            Returns the state of the world (in our case, an image)
        """
        needle_in_tissue = self.needle_in_tissue()
        self.needle.move(action, needle_in_tissue)
        self.update_damage(action)
        running = self.check_status()
        self.t = self.t + 1
        return running

    def needle_in_tissue(self):
        """
            Is the needle in the tissue?
        """
        flag = False
        for s in self.surfaces:
            s_flag = self.needle_in_surface(s)
            flag = flag or s_flag
        return flag

    def needle_in_surface(self, s):
        needle_tip = np.array([self.needle.x, self.height - self.needle.y])
        s_flag = s.poly.contains(Point(needle_tip))
        return s_flag

    def update_damage(self, movement):
        self.damage = 0
        for surface in self.surfaces:
            if self.needle_in_surface(surface):
                surface.calc_damage(movement)
            self.damage += surface.damage

    def check_status(self):
        """
            verify if the game is in a valid state and can
            keep playing
        """
        # is the needle off the screen?
        x = self.needle.x
        y = self.needle.y

        """ have you passed a new gate? """
        if(self.next_gate is not None):
            self.gates[self.next_gate].update([x, self.height - y])
            # if you passed or failed the gate
            if(self.gates[self.next_gate].status != 'next_gate'):
                # increment to the next gate
                self.next_gate = self.next_gate + 1
                if(self.next_gate < self.ngates):
                    # if we have this many gates, set gate status to be next
                    self.gates[self.next_gate].status = 'next_gate'
                else:
                    self.next_gate = None

        """ are you in a valid game configuration? """
        valid_x = x >= 0 and x <= self.width
        valid_y = y >= 0 and y <= self.height
        valid_pos = valid_x and valid_y
        if not valid_pos:
            print("Invalid position")

        # have you hit deep tissue?
        valid_deep = not self._deep_tissue_intersect()
        if not valid_deep:
            print("Punctured deep tissue")

        # check if you have caused too much tissue damage
        valid_damage = self.damage < 100
        if not valid_damage:
            print("Caused too much tissue damage")

        # are you out of time?
        valid_t = self.t < self.max_time
        if not valid_t:
            print("Ran out of game time")

        return valid_pos and valid_deep and valid_t and valid_damage

    def _deep_tissue_intersect(self):
        """
            check each surface, does the needle intersect the
            surface? is the surface deep?
        """
        for s in self.surfaces:
            if s.deep and self.needle_in_surface(s):
                return True
        return False

    def _compute_passed_gates(self):
        passed_gates = 0
        # see if thread_points goes through the gate at any points
        for gate in self.gates:
            if gate.status == 'passed':
                passed_gates = passed_gates + 1

        return passed_gates

    def _gate_score(self):
        '''
                if you pass all gates or there are no gates: 1000 pts
                        don't pass all gates: 1000 * (passed_gates/all_gates) pts
        '''
        passed_gates = self._compute_passed_gates()
        num_gates = len(self.gates)

        if num_gates == 0:
            gate_score = 1000
        else:
            gate_score = 1000 * float(passed_gates)/num_gates
        return gate_score

    def _time_score(self):
        '''
            if more than 1/3 of the time is left: 1000 pts
            else decrease score linearly s.t. score at t=max_time -> 0pts
        '''
        t = self.t
        T = self.max_time

        if t <= (1/3.) * T:
            time_score = 1000
        else:
            m = -1000/(2*T/3.)
            time_score = 1500 + m*t
        return time_score

    def _path_score(self):
        '''
            if path_len <= screen_width -> no penalty
            else decrease score linearly s.t. score at screen_width*3 -> -1000pts
        '''
        w = self._get_path_len()
        W = self.width
        if(w <= W):
            path_score = 0
        else:
            # limit the path length to 3*W
            w = max(w, 3*W)
            path_score = -1000.0/(2*W)*(w - W)
        return path_score

    def _get_path_len(self):
        """
                Compute the path length using the thread points
        """
        path_len = 0
        thread_points = np.array(self.needle.thread_points)
        for i in range(len(thread_points) - 1):
            pt_1 = thread_points[i, :]
            pt_2 = thread_points[i+1, :]

            dX = np.linalg.norm(pt_1 - pt_2)
            path_len = path_len + dX

        return path_len

    def _damage_score(self):
        '''
                damage from tissue btwn [0, 100]. Scale to between [-1000,0]
                damage from deep tissue is -1000
        '''
        damage = -10.0 * self.damage
        if(self._deep_tissue_intersect()):
            print("deep tissue intersect!")
            damage = damage - 1000
        woah()
        damage_score = damage
        return damage_score

    def score(self, print_flag=False):
        """
            compute the score for the demonstration

            gate_score: [0, 1000]
            time_score: [0, 1000]
            path_score: [-1000, 0]
            damage_score: [-2000, 0]

            max score:  2000
            min score: -3000

        """
        gate_score   = self._gate_score()
        time_score   = self._time_score()
        path_score   = self._path_score()
        damage_score = self._damage_score()

        score = gate_score + time_score + path_score + damage_score
        if(print_flag):
            print("Score: " + str(score))
            print("-------------")
            print("Gate Score: " + str(gate_score))
            print("Time Score: " + str(time_score))
            print("Path Score: " + str(path_score))
            print("Damage Score: " + str(damage_score))

        return score

class Gate:
    color_passed = np.array([100., 175., 100.]) / 255
    color_failed = np.array([175., 100., 100.]) / 255
    color1 = np.array([251., 216., 114.]) / 255
    color2 = np.array([255., 50., 12.]) / 255
    color3 = np.array([255., 12., 150.]) / 255

    def __init__(self,env_width,env_height):
        self.x = 0
        self.y = 0
        self.w = 0
        self.top = np.zeros((4,2))
        self.bottom = np.zeros((4,2))
        self.corners = np.zeros((4,2))
        self.width = 0
        self.height = 0
        self.status = None
        self.partner = None
        ''' NOTE Chris implemented 'partner' gates, I think
        we can ignore this and implement gates that have to
        be hit sequentially for now '''

        self.c1 = self.color1
        self.c2 = self.color2
        self.c3 = self.color3
        self.highlight = None

        self.box = None
        self.bottom_box = None
        self.top_box = None

        self.env_width = env_width
        self.env_height = env_height

    def contains(self, poly, traj):
        return [poly.contains(Point(x)) for x in traj]

    def update(self, pos):
        ''' take in current position,
            see if you passed or failed the gate'''
        if((self.status != 'passed') and (self.top_box.contains(Point(pos)) or self.bottom_box.contains(Point(pos)))):
            self.status = 'failed'
            self.c1 = [175/255., 100/255., 100/255.,]
            self.c2 = [175/255., 100/255., 100/255.,]
            self.c3 = [175/255., 100/255., 100/255.,]

        elif(self.box.contains(Point(pos)) and self.status == 'next_gate'):
            self.status = 'passed'
            self.c1 = [100/255., 175/255., 100/255.]
            self.c2 = [100/255., 175/255., 100/255.]
            self.c3 = [100/255., 175/255., 100/255.]

    def draw(self):
        """
        private static final int warning = Color.argb(255, 255, 50, 12);
        """

        axes = plt.gca()
        axes.add_patch(Poly(array_to_tuples(self.corners),color=self.c1))
        if(self.status == 'next_gate'):
            axes.add_patch(Poly(array_to_tuples(self.corners),facecolor=self.c1, edgecolor='green'))

        axes.add_patch(Poly(array_to_tuples(self.top),facecolor=self.c2))
        axes.add_patch(Poly(array_to_tuples(self.bottom),facecolor=self.c3))
        # if next_gate, outline in green

    '''
    Load Gate from file at the current position.
    '''
    def load(self,handle):

        pos = safe_load_line('GatePos',handle)
        cornersx = safe_load_line('GateX',handle)
        cornersy = safe_load_line('GateY',handle)
        topx = safe_load_line('TopX',handle)
        topy = safe_load_line('TopY',handle)
        bottomx = safe_load_line('BottomX',handle)
        bottomy = safe_load_line('BottomY',handle)

        self.x = self.env_width*float(pos[0])
        self.y = self.env_height*float(pos[1])
        self.w = float(pos[2])

        self.top[:,0] = [float(x) for x in topx]
        self.top[:,1] = [float(y) for y in topy]
        self.bottom[:,0] = [float(x) for x in bottomx]
        self.bottom[:,1] = [float(y) for y in bottomy]
        self.corners[:,0] = [float(x) for x in cornersx]
        self.corners[:,1] = [float(y) for y in cornersy]

        # apply corrections to make sure the gates are oriented right
        self.w *= -1
        if self.w < 0:
            self.w = self.w + (np.pi * 2)
        if self.w > np.pi:
            self.w -= np.pi
            self.top = np.squeeze(self.top[np.ix_([2,3,0,1]),:2])
            self.bottom = np.squeeze(self.bottom[np.ix_([2,3,0,1]),:2])
            self.corners = np.squeeze(self.corners[np.ix_([2,3,0,1]),:2])

        self.w -= np.pi / 2

        avgtopy = np.mean(self.top[:,1])
        avgbottomy = np.mean(self.bottom[:,1])

        # flip top and bottom if necessary
        if avgtopy < avgbottomy:
            tmp = self.top
            self.top = self.bottom
            self.bottom = tmp

        # compute gate height and width

        # compute other things like polygon
        self.box        = Polygon(self.corners)
        self.top_box    = Polygon(self.top)
        self.bottom_box = Polygon(self.bottom)


class Surface:

    def __init__(self,env_width,env_height):
        self.deep = False
        self.corners = None
        self.color = None
        self.damage = 0 # the damage to this surface

        self.env_width = env_width
        self.env_height = env_height

        self.poly = None

    def draw(self):
        ''' update damage and surface color '''
        #self.compute_damage()
        #self.update_color() # based on the amount of damage
        axes = plt.gca()
        axes.add_patch(Poly(array_to_tuples(self.corners), color=self.color))
    '''
    Load surface from file at the current position
    '''
    def load(self, handle):
        isdeep = safe_load_line('IsDeepTissue',handle)

        sx = [float(x) for x in safe_load_line('SurfaceX',handle)]
        sy = [float(x) for x in safe_load_line('SurfaceY',handle)]
        self.corners = np.array([sx,sy]).transpose()
        self.corners[:,1] = self.env_height - self.corners[:,1]


        self.deep = isdeep[0] == 'true'
        self.deep_color = np.array([207., 69., 32.]) / 255
        self.light_color = np.array([232., 146., 124.]) / 255
        self.color = np.array(self.deep_color if self.deep else self.light_color)

        self.poly = Polygon(self.corners)

    def calc_damage(self, movement):
        dw = movement[1]
        if abs(dw) > 0.02:
            self.damage += (abs(dw)/2.0 - 0.01) * 100
            if self.damage > 100:
                self.damage = 100
            self.update_color()

    def update_color(self):
        alpha = self.damage / 100.
        beta = (100. - self.damage) / 100.
        self.color = beta * self.light_color + alpha * self.deep_color

class Needle:

    def __init__(self, env_width, env_height):
        self.x = 96     # read off from saved demonstrations as start x
        self.y = env_height - 108    # read off from saved demonstrations as start y
        self.w = math.pi
        self.corners = None

        self.max_dXY      = 75
        self.length_const = 0.08
        self.scale        = np.sqrt(env_width**2 + env_height**2)
        self.is_moving    = False

        self.env_width = env_width
        self.env_height = env_height

        self.needle_color  = np.array([134., 200., 188.])/255
        self.thread_color  = np.array([167., 188., 214.])/255

        self.thread_points = []

        self.load()

    def draw(self):
        self._draw_needle()
        self._draw_thread()

    def _compute_corners(self):
        """
            given x,y,w compute needle corners and save
        """
        w = self.w
        x = self.x
        y = self.env_height - self.y

        top_w = w - math.pi/2
        bot_w = w + math.pi/2

        length = self.length_const * self.scale

        top_x = x - (0.01 * self.scale) * math.cos(top_w) + \
                (length * math.cos(w))
        top_y = y - (0.01 * self.scale) * math.sin(top_w) + \
                (length * math.sin(w))
        bot_x = x - (0.01 * self.scale) * math.cos(bot_w) + \
                (length * math.cos(w))
        bot_y = y - (0.01 * self.scale) * math.sin(bot_w) + \
                (length * math.sin(w))

        self.corners = np.array([[x, y], [top_x, top_y], [bot_x, bot_y]])

    def _draw_needle(self):
        axes = plt.gca()
        axes.add_patch(Poly(array_to_tuples(self.corners),
            color=self.needle_color))

    def _draw_thread(self):
        if len(self.thread_points) > 0:
            thread_points = np.array(self.thread_points)
            plt.plot(thread_points[:,0],
                    self.env_height - thread_points[:, 1],
                    c=self.thread_color)

    def load(self):
        """
            Load the current needle position
        """
        # compute the corners for the current position
        self._compute_corners()
        self.poly = Polygon(self.corners)

    def move(self, movement, needle_in_tissue):
        """
            Given an input, move the needle. Update the position, orientation,
            and thread path in android game movement is specified by touch
            points. last_x, last_y specify the x,y in the previous time step
            and x,y specify the current touch point

            dx = x - last_x
            dy = y - last_y
            w  = atan2(dy/dx)

            right now we assume you take in dx and dy
            (since we can directly pass that)

        """
        dX = movement[0]
        dw = movement[1]

        if(needle_in_tissue):
            dw = 0.5 * dw
            if(abs(dw)> 0.01):
                dw = 0.02 * np.sign(dw)

        self.w = self.w + dw
        self.x = self.x + dX * math.cos(self.w)
        self.y = self.y - dX * math.sin(self.w)

        self._compute_corners()
        self.poly = Polygon(self.corners)
        self.thread_points.append((self.x, self.y))

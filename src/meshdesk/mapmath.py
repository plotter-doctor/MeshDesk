"""Portable equivalents of the pinned web client's map overlay rules."""
import math


def signal_color(snr,rssi=None):
    if snr>-7 and (rssi is None or rssi>-115):return '#00ff00'
    if snr>-15 and (rssi is None or rssi>-126):return '#ffe600'
    return '#f7931a'


def precision_meters(bits):
    return math.floor(.5*2**(32-int(bits))*1e-7*111319.490793+.5) if 0<int(bits)<=32 else 0


def fan_offsets(size,key):
    h=5381
    for char in key:h=(h*33+ord(char))&0xffffffff
    start=(h%360)*math.pi/180
    radius=10+5*size
    return [(radius*math.cos(start+i*2*math.pi/size),radius*math.sin(start+i*2*math.pi/size)) for i in range(size)]


def heat_weight(snr,mode):
    if mode=='density':return 1.0
    return max(0.,min(1.,(snr+20)/30)) if snr is not None else 0.


def heat_radius(zoom):
    return 2+2*zoom if zoom<=9 else 20+10*min(6,zoom-9)/6


def heat_color(value):
    stops=((33,102,172,0),(103,169,207,179),(209,229,240,179),
           (253,219,199,179),(239,138,98,179),(178,24,43,179))
    step=max(0,min(5,value*5));index=min(4,int(step));weight=step-index
    return tuple(round(a+(b-a)*weight) for a,b in zip(stops[index],stops[index+1]))


def segment_distance(x,y,ax,ay,bx,by):
    length=(bx-ax)**2+(by-ay)**2
    t=max(0,min(1,((x-ax)*(bx-ax)+(y-ay)*(by-ay))/length)) if length else 0
    return math.hypot(x-ax-t*(bx-ax),y-ay-t*(by-ay))


def nice_scale(latitude,zoom,max_pixels=100):
    meters_per_pixel=156543.033928*math.cos(math.radians(latitude))/2**zoom
    maximum=max_pixels*meters_per_pixel
    base=10**math.floor(math.log10(maximum))
    meters=max(v*base for v in (1,2,5,10) if v*base<=maximum)
    return meters/meters_per_pixel,(f'{meters/1000:g} km' if meters>=1000 else f'{meters:g} m')

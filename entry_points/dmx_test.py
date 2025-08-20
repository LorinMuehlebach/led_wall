
import time

from led_wall.PyDMX import PyDMX

dmx = PyDMX('COM5')


while True:
    dmx.set_data(1,255) 
    dmx.set_data(2,0) 
    dmx.set_data(3,0) 
    #dmx.set_data(4,255) 
    dmx.set_data(5,0) 
    dmx.send() #takes 250ms
    time.sleep(1)  # Sleep for 1 second
import machine
from machine import Pin
from utime import sleep_ms

from main_program.main import Runner

#############################################

# program for the comm block (almost the same as the motion block)

#############################################

print('comm block boot start')

# global LED Pin
led_red = Pin(19, Pin.OUT)
led_green = Pin(20, Pin.OUT)


sleep_ms(4000)
led_red.value(1); led_green.value(0)

# Always queenness == False for the comm block.

r = Runner(False)
r.main_runner()
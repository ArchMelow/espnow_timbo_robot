from machine import Pin, ADC, PWM, Timer, enable_irq, reset, I2C
from utime import sleep_ms, sleep, ticks_ms, ticks_diff
import asyncio
import espnow
import network
import json
import math
import os
import binascii
import socket
import gc
import sys

'''
defines/initializes IO for a single motion block device.
'''
class BlockIODevices:
    
    def __init__(self, is_queen = False):
        # block device Queen or Slave?
        self.is_queen = is_queen
        
        # basic IO Pin initialization 
        self.led_red = PWM(Pin(19, Pin.OUT))
        self.led_green = PWM(Pin(20, Pin.OUT))
        self.led_red.freq(1000)
        self.led_green.freq(1000)
        self.set_led_color('none') # turn the LED off
        
        self.cpu_on_pin = Pin(8, Pin.OUT)
        self.cpu_on_pin.value(1) 
        self.bttn = Pin(39, Pin.IN, Pin.PULL_UP)
        self.backward_motor = Pin(33, Pin.OUT)
        self.forward_motor = Pin(32, Pin.OUT)
        self.nSleep = Pin(7, Pin.OUT)
        self.adc = ADC(Pin(36), atten=ADC.ATTN_6DB) # analog-to-digital conversion on Pin 36
        self.dummy_pin = Pin(27, Pin.OUT)
        self.callback_pin = Pin(26, Pin.OUT)
        self.mac_addr = None # the hexadecimal MAC address of this motion block.
        
        # PWM instances, PWM duty value 
        self.backward_pwm = PWM(self.backward_motor, freq = 10000)
        self.forward_pwm = PWM(self.forward_motor, freq = 10000)
        self.duty_cycle = 0
        self.prev_duty_error = 0
        
        # motor duty memory (empty) - could cause memory overflow
        # now maintains 5 memory arrays, could be chosen with the command via the download mode from the queen (mode 4)
        self.duty_memories = [[] for _ in range(5)]
        self.cur_mem_idx = 0 # currently used memory index (defaults to 0)
        self.duty_mem_limit = 100000 # memory limit for each duty memory array.
        self.mem_counter = 0
        self.recorded_adc = 0
        
        # recording motor values
        self.prev_rec = -1 # first value has to be recorded (adc could not be negative)
        
        # kill itself if there was no user-interaction for a while
        self.kill_timer = 0
        
        
        # received flag/message for the callback
        self.received_flag = False
        self.received_msg = None
        self.received_mac = None
        self.received_duty = 0
        self.queen_mac = None
        
        # espnow and STA instance
        self.sta = network.WLAN(network.STA_IF)
        self.e = espnow.ESPNow()
        
        # start connection
        self.start_connection()
        
        # network table 
        print(f'mac_addr init : {self.mac_addr}')
        self.net_table = [bytes.fromhex(self.mac_addr)] if self.mac_addr else []
        print(f'net table init : {self.net_table}')
        
        # DOES NOT USE THIS PART YET
        # read/init network table
        # check if table file exists
        init_flag = True
        try: # there exists prior network tables setting, load it.
            os.stat('net_table.txt')
        except OSError: # file does not exist, create a new one.
            init_flag = False
        
        #print(init_flag)
        
        self.end_connection()
        
        self.timer = Timer(1)  #LEE (init a timer object with ID 1)
        
    def start_connection(self):
        self.sta.active(True)
        self.mac_addr = binascii.hexlify(self.sta.config('mac')).decode() # current device's MAC addr (bytestring decoded)
        
        self.e.active(True)
        # add mac addr for broadcasting
        self.e.add_peer(b'\xff' * 6)
        
    def end_connection(self):
        # does not strictly end connection; (init to None & gc.collect())
        self.sta.active(False)
        self.e.active(False)

    
    def stop_motor(self): 
        self.backward_pwm.duty(0)
        self.forward_pwm.duty(0)
        self.nSleep.value(False)
       
    '''
    doesn't matter if it is async or not.
    '''
    async def async_move_motor(self, cur_value):
        self.move_motor(cur_value)
        asyncio.sleep(0.000001) # 0.01 ms
    
    def sync_move_motor(self, cur_value):
        self.move_motor(cur_value)
        sleep_ms(1)
       
    '''
    arguments:
    
    cur_value : the ADC(motor) value which is desired (0 ~ 4095)
    adc_value : the actual ADC(motor) value from the sensor (0 ~ 4095)

    Applies PID to control the motor.
    
    '''
    def move_motor(self, cur_value):
        if cur_value == -1:
            return # do nothing
        
        K_p = 3; K_i = 0
        #cur_value = 500
        adc_value = self.adc.read()
        duty_error_diff = adc_value - cur_value
        duty_error = duty_error_diff
        new_duty_error = duty_error + self.prev_duty_error
        
        if duty_error > 3500:
            duty_error -= 4096
        elif duty_error < -3500:
            duty_error += 4096
            
        corrected_duty = int(K_p * abs(duty_error)) + int(K_i * new_duty_error)
        corrected_duty = max(0, min(corrected_duty, 1023))
        
        # correct current duty value
        if duty_error > 0: # backwards
            self.forward_pwm.duty(0)
            self.backward_pwm.duty(corrected_duty)
        elif duty_error < 0: # forwards
            self.forward_pwm.duty(corrected_duty)
            self.backward_pwm.duty(0)
        else: # don't move
            self.forward_pwm.duty(0)
            self.backward_pwm.duty(0)
            
        # save duty error to previous duty error
        self.prev_duty_error = duty_error
        
        
    '''
    record the ADC(motor) sensor value almost every 30ms
    to lower the possibility where the motor moves greater than 3500, (design issue)
    tries to record only the sensor values where |prev-cur| < 3500.
    
    multicast sensor data to the slaves in its group if it is the queen recording.
    '''
    async def record_motor(self, flag):
        # overwrite (until the memory is full)
        adc = self.adc.read()
        # index for the currently used memory index
        i = self.cur_mem_idx
        if (len(self.duty_memories[i]) < self.duty_mem_limit):
            if self.mem_counter == 30 and abs(self.prev_rec - adc) < 3500:
                #print(self.prev_rec, adc)
                self.prev_rec = adc
                self.duty_memories[i].append(adc)
                if self.is_queen and len(self.net_table) > 1: # if this is queen in the record mode, send the duty value to the group
                    # takes approx. 2.5ms to send
                    if flag:
                        self.e.send(None, json.dumps({'tag':'duty',
                                                      'is_queen':True,
                                                      'val':adc}))
                    
                
            self.prev_rec = adc
            self.mem_counter = (self.mem_counter + 1) % 31 # increment counter
    
    '''
    save motor data as a file (duty.dat)
    '''
    def save_motor_data(self):
        # simply overwrite
        with open('./motor_data/duty.dat', 'w') as f:
            for lst in self.duty_memories:
                for i, d in enumerate(lst):
                    f.write(d)
                    if i < len(lst) - 1:
                        f.write(',')
                f.write('\n') # add newline
    
    '''
    after some time being idle (mode not changed),
    powers off the motion block to save battery.
    '''
    def block_power_if_idle(self):
        if self.kill_timer and self.kill_timer % 200000 == 0:  #10000:20 sec, 200000
            print('Power off for saving battery')
            sleep_ms(1000)
            self.cpu_on_pin.value(0)
    
    '''
    set LED color based on the string given
    '''
    ### LED color manipulation using PWM ###
    def set_led_color(self, color):
        if color == 'r': # red
            self.led_red.duty_u16(65535)
            self.led_green.duty_u16(0)
        if color == 'g': # green
            self.led_red.duty_u16(0)
            self.led_green.duty_u16(65535)
        if color == 'y': # yellow
            self.led_red.duty_u16(10000)
            self.led_green.duty_u16(65535)
        if color == 'o': # orange
            self.led_red.duty_u16(65535)
            self.led_green.duty_u16(65535)
        if color == 'none': # off
            self.led_red.duty_u16(0)
            self.led_green.duty_u16(0)
        # add more colors
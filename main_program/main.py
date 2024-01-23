from machine import Pin, ADC, PWM, Timer, enable_irq, disable_irq
from utime import sleep_ms, sleep, ticks_ms, ticks_diff
import asyncio
from asyncio import Lock
import espnow
import network
import json
import math
import os
import binascii


# create a network table, for the first time.
def create_network_table(filename, net_dict):
    with open(filename, 'w') as f:
        print(net_dict['mac_addr'] + ' ')
        f.write(net_dict['mac_addr'] + ' ') # append a space (for split())
    
# load prior network table settings from the file.
# also, register peers in the file loaded.
def load_network_table(filename, net_dict):
    f = open(filename, 'r', encoding='utf-8')
    print(f.read())
    
    with open(filename, 'r') as f:
        mac_list = f.read().split(' ') # table entries (MAC addrs)

    for m in mac_list:
        if m:  # Check if the string is not empty
            net_dict['espnow'].add_peer(m.strip()) # add entries as peers of this motion block.
    

'''
defines/initializes IO for a single motion block device.
'''
class BlockIODevices:
    
    def __init__(self, is_queen = False):
        # block device Queen or Slave?
        self.is_queen = is_queen
        
        # basic IO Pin initialization 
        self.led_red = Pin(20, Pin.OUT)
        self.led_green = Pin(19, Pin.OUT)
        self.which_led = 0
        self.bttn = Pin(35, Pin.IN, Pin.PULL_UP)
        self.backward_motor = Pin(33, Pin.OUT)
        self.forward_motor = Pin(32, Pin.OUT)
        self.nSleep = Pin(7, Pin.OUT)
        self.adc = ADC(Pin(36), atten=ADC.ATTN_6DB) # analog-to-digital conversion on Pin 36
        self.dummy_pin = Pin(25, Pin.OUT)
        self.mac_addr = None
        
        # PWM instances, PWM duty value 
        self.backward_pwm = PWM(self.backward_motor, freq = 10000)
        self.forward_pwm = PWM(self.forward_motor, freq = 10000)
        self.duty_cycle = 0
        self.prev_duty_error = 0
        
        # motor duty memory (empty) - could cause memory overflow
        self.duty_memory = []
        #self.duty_memory = [b'1024', b'2048', b'0']
        self.duty_mem_limit = 100000
        self.mem_counter = 0
        self.summer = 0
        
        # recording motor values
        self.prev_rec = -1 # first value has to be recorded (adc could not be negative)
        
        
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
        
        # network table (shared variable)
        print(f'mac_addr init : {self.mac_addr}')
        self.net_table = [bytes.fromhex(self.mac_addr)] if self.mac_addr else []
        print(f'net table init : {self.net_table}')
        
        # read/init network table
        # check if table file exists
        init_flag = True
        try: # there exists prior network tables setting, load it.
            os.stat('net_table.txt')
        except OSError: # file does not exist, create a new one.
            init_flag = False
        
        print(init_flag)
        
        #self.net_table = load_network_table('net_table.txt', self.net_dict) if init_flag else create_network_table('net_table.txt', self.net_dict)
        self.end_connection()
        
    def start_connection(self):
        # from the documentation 
        self.sta.active(True)
        self.mac_addr = binascii.hexlify(self.sta.config('mac')).decode() # current device's MAC addr (bytestring decoded)
        
        self.e.active(True)
        # add mac for broadcasting
        self.e.add_peer(b'\xff' * 6)
        
    def end_connection(self):
        self.sta.active(False)
        self.e.active(False)

    ## control motor ##
    def stop_motor(self):
        self.backward_pwm.duty(0)
        self.forward_pwm.duty(0)
        self.nSleep.value(False)
       
    async def async_move_motor(self, cur_value):
        self.move_motor(cur_value)
        asyncio.sleep(0.00001) # 0.01 ms
    
    def sync_move_motor(self, cur_value):
        self.move_motor(cur_value)
        sleep_ms(1)
       
    def move_motor(self, cur_value):
        #print('move motor called')
        if cur_value == -1:
            return # do nothing
        
        #print(f'curval: {cur_value}')
        
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
        #print('move motor end well')
            
    async def record_motor(self):
        # overwrite (until the memory is full)
        adc = self.adc.read()
        # for every cycle
        # if current read adc value diff is larger than 10 compared to the previous adc, add to mem
        if (len(self.duty_memory) < self.duty_mem_limit):
            if self.mem_counter == 440 and abs(self.prev_rec - adc) < 3500:
                self.duty_memory.append(adc)
                if self.is_queen and len(self.net_table) > 1: # if this is queen in the record mode, send the duty value to the group
                    self.e.send(None, json.dumps({'tag':'duty',
                                                  'is_queen':True,
                                                  'val':adc}))
            self.prev_rec = adc
            self.mem_counter = (self.mem_counter + 1) % 441 # increment counter    
            
            
            
        
        
        

    def is_led_red_on(self):
        return self.led_red.value()
    
    def is_led_green_on(self):
        return self.led_green.value()
    
    
    # advertise {mac, queenness, button_press_duration} - to the peer devices (broadcast)
    def advertise_bttn(self):
        self.e.send(b'\xff' * 6, json.dumps({'tag':'button_event',
                                                  'mac_addr':self.mac_addr,
                                                  'is_queen':self.is_queen}))
        
    def advertise_one_to_all(self):
        self.e.send(b'\xff' * 6, json.dumps({'tag':'one_to_all',
                                                   'mac_addr':self.mac_addr,
                                                   'is_queen':self.is_queen}))
        
        
'''
code runner.
'''
class Runner:
    def __init__(self, is_queen=False):
        # init a motion block
        self.mb = BlockIODevices(is_queen) 
        # manage button
        self.prev_bttn = self.mb.bttn.value()
        self.longpress_cnt = 0
        # device mode (0: idle, 1: record, 2: play)
        self.prev_mode = 0
        self.mode = 0
        
        
        # shared variable
        self.grouping_flag = False
        # motor counter
        self.duty_mem_idx = 0
        self.motor_update_cnt = 0
        
        # record and play at the same time. (mode 3)
        self.motor_mem_cnt = 0
        self.cur_duty = 0 
        
    def recv_cb_queen(self, e):
        while True:
            mac,msg = e.irecv(0)
            if msg is None:
                break
            print(f'received {msg} from the callback')
            self.mb.received_msg = bytes(msg.decode().replace('\x00', '').encode('utf-8'))
            self.mb.received_mac = mac
            
            json_msg = json.loads(msg)
            if json_msg['tag'] == 'play':
                self.mode = 2 # job done
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer
                

    def recv_cb_slave(self, e):
        while True:
            mac,msg = e.irecv(0)
            if msg is None:
                return
            print(f'received {msg} from the callback')
            self.mb.received_msg = bytes(msg.decode().replace('\x00', '').encode('utf-8'))
            self.mb.received_mac = mac
            json_msg = json.loads(msg)
            if json_msg['is_queen']:
                if json_msg['tag'] == 'distribute':
                    self.mb.net_table = [bytes.fromhex(hm) for hm in json_msg['net_table']] # overwrite (order not considered) - job done
                    print(f'slave net table : {self.mb.net_table}')
                    self.mode = 3 # record and play mode
                    self.mb.received_msg = None
                    self.mb.received_mac = None # clear the buffer
                if json_msg['tag'] == 'duty':
                    self.mb.received_duty = int(json_msg['val']) # save the duty sent from the queen (some values could be ignored by the slave!)
                    self.mb.received_msg = None
                    self.mb.received_mac = None # clear the buffer
                    
                        
                    
            if json_msg['tag'] == 'play':
                self.mode = 2 # job done
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer
                
            
            
                
    
    async def button(self):
        #if self.mode == 2:
            #print('button called')
        bttn_val = self.mb.bttn.value()
        if not bttn_val and self.prev_bttn:
            print('bttn on')
            self.longpress_cnt = 0
        elif bttn_val and not self.prev_bttn and self.longpress_cnt < 700:
            print('bttn off - toggled')
            self.longpress_cnt = 0
            self.mode = (self.mode + 1) % 3 if self.mode < 3 else 0
        elif not bttn_val and not self.prev_bttn:
            #if self.mode == 2:
                #self.mb.sync_move_motor(int(self.mb.duty_memory[self.duty_mem_idx]))
            self.longpress_cnt += 1
        else: # all off
            #if self.mode == 2:
                #self.mb.sync_move_motor(int(self.mb.duty_memory[self.duty_mem_idx]))
            self.longpress_cnt = 0
        self.prev_bttn = bttn_val
        asyncio.sleep_ms(1) # 10ms
    
    
    
    
    async def runner(self):
        # button/motor based interaction
        # functionalities (each task by index):
        # task 0. record (with the button & motor)
        # task 1. play (with the button & motor)
        # task 2. activate STA and espnow and receive messages with timeout & grouping/ungrouping/syncing (while button is pressed) 
        # locks for each task (since there only runs one task at a time)
        
        # keep the network alive.
        '''
        if not self.mb.is_queen:
        '''
        self.mb.start_connection()
        # callback (should be shortest as possible in consuming time)
        if self.mb.is_queen:
            self.mb.e.irq(self.recv_cb_queen)
        else:
            self.mb.e.irq(self.recv_cb_slave)
        
        # some time for the callback to settle
        await asyncio.sleep_ms(100)
        
        # main routine
        while True:
            
            # if mode changed
            if self.mode != self.prev_mode:
                self.prev_mode = self.mode
                if self.mode == 0: # idle
                    
                    # unset LED
                    self.mb.led_red.value(0)
                    self.mb.led_green.value(0)
                    
                    self.mb.stop_motor() # turn off the motor
                elif self.mode == 1: # record
                    self.mb.stop_motor()
                    
                    # set red LED
                    self.mb.led_red.value(1)
                    self.mb.led_green.value(0)
                    
                    self.mb.duty_memory = [] # reset 
                elif self.mode == 2: # turn on the motor
                    
                    # set green LED
                    self.mb.led_red.value(0)
                    self.mb.led_green.value(1)
                    
                    if len(self.mb.net_table) > 1:
                        # multicast to peers to change the mode to 2 (play)
                        self.mb.e.send(None, json.dumps({'tag':'play',
                                                         'is_queen':self.mb.is_queen}))
                    self.duty_mem_idx = 0 # reset the counter
                    self.motor_update_cnt = 0
                    print('duty mem : ', self.mb.duty_memory)
                    self.mb.nSleep(True)
                elif self.mode == 3: # record and play (unreachable by the user button input)
                    
                    # set yellow LED
                    self.mb.led_red.value(1)
                    self.mb.led_green.value(1)
                    
                    self.motor_mem_cnt = 0 # reset the counter
                    self.mb.duty_memory = []
                    self.mb.nSleep(True) # enable the motor
                    
                print(f'mode changed to {self.mode}')
            
            if self.mode == 0: # idle mode
                tasks = [self.button()]
                res = await asyncio.gather(*tasks)
            
                # if a queen and the slave's button are both pressed within the timediff of approx. 2s
                # we define it as the 'buttons pressed at the same time'
                if self.longpress_cnt == 700:
                    print('bttn held for long time..')
                    
                    # correct grouping based on callback
                    if self.mb.is_queen:
                        
                        
                        await asyncio.sleep_ms(1500) # wait 1.5s (listen)
                        # if queen received None, one-to-all
                        # if queen received something, grouping
                        # think of other cases
                        
            
                        if self.mb.received_msg is None:
                            # if net table is not empty, multicast to peers
                            
                            hex_net_table = [binascii.hexlify(m).decode() for m in self.mb.net_table]
                            if len(self.mb.net_table) > 1:
                                self.mb.e.send(None, json.dumps({'tag':'distribute',
                                                                 'is_queen':True,
                                                                 'net_table':hex_net_table}))
                                self.mode = 1 # change to recording mode
                            
                            
                        else: # grouping / ungrouping
                            msg_obj = json.loads(self.mb.received_msg)
                            hex_mac = binascii.hexlify(self.mb.received_mac).decode()
                            
                            if self.mb.received_mac in self.mb.net_table: # ungrouping
                                self.mb.net_table.remove(self.mb.received_mac)
                                self.mb.e.send(self.mb.received_mac, json.dumps({'tag':'ungrouping',
                                                                                 'is_queen':True}))
                                self.mb.e.del_peer(self.mb.received_mac)
                            
                            else: # grouping
                                self.mb.net_table.append(self.mb.received_mac)
                                self.mb.e.add_peer(self.mb.received_mac)
                                self.mb.e.send(self.mb.received_mac, json.dumps({'tag':'grouping',
                                                                                 'is_queen':True}))
                                               
                        
                        # clear the flag to receive new message
                        self.mb.received_msg = None
                        self.mb.received_mac = None
                        
                        
                        
                        
                    else: # slave (no conflict with 'distribute', this waits 1s only if longbttn pressed.)
                        # send grouping message
                        self.mb.e.send(b'\xff'*6, json.dumps({'tag':'grouping', 'is_queen':self.mb.is_queen}))
                        # if queen mac addr is in net table, ungroup/ else group
                        await asyncio.sleep_ms(3500) # wait 3.5s (expect button async)
                        
                        # if no received message, queen was not pressed at the same time (approx.).
                        if self.mb.received_msg is None:
                            pass # do nothing
                        
                        else:
                            # assume we received the msg
                            msg_obj = json.loads(self.mb.received_msg)
                            queen_mac = self.mb.received_mac
                            
                            if msg_obj['tag'] == 'grouping': # group with the queen
                                if queen_mac not in self.mb.net_table:
                                    self.mb.net_table.append(queen_mac)
                                    self.mb.e.add_peer(queen_mac)
                            elif msg_obj['tag'] == 'ungrouping': # ungroup with the queen
                                if queen_mac in self.mb.net_table:
                                    self.mb.net_table.remove(queen_mac)
                                    self.mb.e.del_peer(queen_mac)
                            
                        
                        # clear the flag to receive new message
                        self.mb.received_msg = None
                        self.mb.received_mac = None
                    
                    
                    print(f'net table : {self.mb.net_table}')
                    
                    
                
            if self.mode == 1: # record mode
                tasks = [self.button(), self.mb.record_motor()]
                #tasks = [self.button()]
                res = await asyncio.gather(*tasks)
                if self.longpress_cnt == 700:
                    print('bttn held for long time.. do nothing')
            
            if self.mode == 2: # play mode
                #print(int(self.mb.duty_memory[self.duty_mem_idx]))
                if not self.mb.duty_memory: # no memory (empty)
                    tasks = [self.button()]
                    res = await asyncio.gather(*tasks)
                else:
                    if self.duty_mem_idx >= len(self.mb.duty_memory):
                        print(self.duty_mem_idx, self.mb.duty_memory)

                    tasks = [self.button(), self.mb.async_move_motor(int(self.mb.duty_memory[self.duty_mem_idx]))]
                    res = await asyncio.gather(*tasks)
                    #print(self.mb.adc.read())
                    if self.longpress_cnt == 700:
                        print('bttn held for long time.. do nothing')
                    if self.motor_update_cnt >= 300:
                        self.duty_mem_idx = (self.duty_mem_idx + 1) % len(self.mb.duty_memory)
                        self.motor_update_cnt = 0
                        #print(self.mb.adc.read())
                    self.motor_update_cnt = (self.motor_update_cnt + 1) % 301
            
            if self.mode == 3: # record and play mode
                tasks = [self.button(), self.mb.async_move_motor(int(self.cur_duty))]
                res = await asyncio.gather(*tasks)
                if self.longpress_cnt == 700:
                    print('bttn held for long time.. do nothing')
                if self.motor_mem_cnt >= 300: # record and play
                    self.cur_duty = self.mb.received_duty # update the duty
                    self.mb.duty_memory.append(self.cur_duty)
                self.motor_mem_cnt = (self.motor_mem_cnt + 1) % 301
                    
                    
                
                
                
                
            
    # wrapper function for the runner()
    def main_runner(self):
        asyncio.run(self.runner())
    
                    
        
                
'''
main part. (modify this part to set queenness)
'''

with open('../is_queen.conf', 'r') as f:
    queenness = f.read()
r = Runner(is_queen=queenness)
r.main_runner()







    





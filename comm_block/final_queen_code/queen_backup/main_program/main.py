from machine import Pin, ADC, PWM, Timer, enable_irq, disable_irq, reset, I2C
from utime import sleep_ms, sleep, ticks_ms, ticks_diff
import asyncio
from asyncio import Lock
import espnow
import network
import json
import math
import os
import binascii
import socket
import gc
import uselect
import sys
import micropython
#from src.sensor import LSM9DS1
from src.motion_block.BlockIODevices import BlockIODevices
from src.webserver.webserver import open_server
from src.rl_serial.rl_serial import play_rl
from src.espnow.grouping import grouping

'''
TODO :

- load network table from file
- save network table to file
- load motor data from file 
- download motor data from the https server (mode 4) - done
- add OTA update functionality to the https server (mode 4) -> model and main.py
'''
   
'''
main.py

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
        
        # motor counter
        self.duty_mem_idx = 0
        self.motor_update_cnt = 0
        
        # record and play at the same time. (mode 5)
        self.motor_mem_cnt = 0
        self.cur_duty = 0
        
        # play flag (play memory every 50ms timer tick)
        self.p_flag = 0  #LEE (set every 50ms timer interrupt)
        
        # stdin event handler (for serial communication with PC)
        self.spoll = uselect.poll()
        self.spoll.register(sys.stdin, uselect.POLLIN)
        
        # for RL mode
        self.recv_flags = {} # to represent two slaves in RL mode
        # init ex) {'mac_addr1' : True, 'mac_addr2' : True}
        self.recv_states = {} # 11(12)D list for each of the 2 slaves
    
    '''
    ESPNow callback function for the queen
    '''
    def recv_cb_queen(self, e):
        while True:
            mac,msg = e.irecv(0)
            if msg is None:
                break
            #print(f'received {msg} from the callback')
            self.mb.received_msg = bytes(msg.decode().replace('\x00', '').encode('utf-8'))
            self.mb.received_mac = mac
            
            json_msg = json.loads(msg)
            print(json_msg)
            if json_msg['tag'] == 'play':
                self.mode = 2 # job done
                #self.prev_mode = 2 # prevent the msg ('play') sent from this device
                
                # set green LED
                self.mb.set_led_color('g')
                
                self.duty_mem_idx = 0 # reset the counter
                self.motor_update_cnt = 0
                self.mb.nSleep(True)
                
                # set timer for playing recorded memory
                self.p_flag = 0   #LEE
                self.mb.timer.init(period=50, mode=Timer.PERIODIC, callback=self.periodic_interrupt)
                
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer
            
            # all slaves stop together
            if json_msg['tag'] == 'idle' or json_msg['tag'] == 'stop':
                self.mode = 0
                self.mb.received_msg = None
                self.mb.received_mac = None
            if json_msg['tag'] == 'record':
                self.mode = 1
                self.prev_mode = 1 # mode 5 not triggered from the slave (IMPORTANT)
                # set red LED
                self.mb.set_led_color('r')     
                self.duty_mem_idx = 0 # reset the counter
                self.motor_update_cnt = 0
                i = self.mb.cur_mem_idx
                self.mb.duty_memories[i] = [] # empty memory
                
                self.mb.received_msg = None
                self.mb.received_mac = None
                
            ## erase this part after test (comm block)    
                
            if json_msg['tag'] == 'distribute_comm':
                new_table = [bytes.fromhex(hm) for hm in json_msg['net_table']] # overwrite (order not considered) - job done
                for m in new_table:
                    if m not in self.mb.net_table:
                        self.mb.e.add_peer(m)
                        self.mb.net_table.append(m) # add m to the net table
                print(f'net table : {self.mb.net_table}')
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer    
                
            ## END OF TEST CODE ##   
                
            if json_msg['tag'] == 'rl_feedback':
                i = self.bytes_to_hex(self.mb.received_mac)
                self.recv_flags[i] = True
                self.recv_states[i] = json_msg['next_state'] # 10(11)D list
                self.mb.received_msg = None
                self.mb.received_mac = None
                
    '''
    ESPNow callback function for the slaves
    '''
    def recv_cb_slave(self, e):
        while True:
            mac,msg = e.irecv(0)
            if msg is None:
                break    
            self.mb.callback_pin.value(1)
            #print(f'received {msg} from the callback')
            self.mb.received_msg = bytes(msg.decode().replace('\x00', '').encode('utf-8'))
            self.mb.received_mac = mac
            json_msg = json.loads(msg)
            if json_msg['is_queen']:
                if json_msg['tag'] == 'distribute':
                    new_table = [bytes.fromhex(hm) for hm in json_msg['net_table']] # overwrite (order not considered) - job done
                    for m in new_table:
                        if m not in self.mb.net_table:
                            self.mb.e.add_peer(m)
                            self.mb.net_table.append(m) # add m to the net table
                    print(f'slave net table : {self.mb.net_table}')
                    self.mb.received_msg = None
                    self.mb.received_mac = None # clear the buffer
                if json_msg['tag'] == 'record':
                    self.mode = 5 # change mode to 5
                    self.mb.received_msg = None
                    self.mb.received_mac = None
                if json_msg['tag'] == 'duty' and self.mode == 5:
                    self.mb.received_duty = int(json_msg['val']) # save the duty sent from the queen (some values could be ignored by the slave!)
                    # currently used memory index
                    i = self.mb.cur_mem_idx
                    self.mb.duty_memories[i].append(self.mb.received_duty)
                    self.mb.received_msg = None
                    self.mb.received_mac = None # clear the buffer
                if json_msg['tag'] == 'idle' or json_msg['tag'] == 'stop':
                    self.mode = 0
                    self.mb.received_msg = None
                    self.mb.received_mac = None
                
            if json_msg['tag'] == 'stop':
                self.mode = 0
                self.mb.received_msg = None
                self.mb.received_mac = None
            
            
            if json_msg['tag'] == 'play':
                    
                self.mode = 2 # job done
                #self.prev_mode = 2
                
                # set green LED
                self.mb.set_led_color('g')
                                               
                self.duty_mem_idx = 0 # reset the counter
                self.motor_update_cnt = 0
                self.mb.nSleep(True)
            
                # set timer for playing recorded memory
                self.p_flag = 0   #LEE
                self.mb.timer.init(period=50, mode=Timer.PERIODIC, callback=self.periodic_interrupt)
                    
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer
            
            if json_msg['tag'] == 'start_rl':
                self.mode = 3
                self.prev_mode = 3
                self.mb.set_led_color('none')
                self.mb.nSleep(False)
                
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer
                
                
    '''
    function that can check two button states (toggle, long press)
    checks the button synchronously every 1ms
    '''
    
    def button(self):   #LEE
        bttn_val = self.mb.bttn.value()
        if bttn_val and not self.prev_bttn:
            print('bttn on')
            self.longpress_cnt = 0
        elif not bttn_val and self.prev_bttn and self.longpress_cnt < 700:
            print('bttn off - toggled')
            self.longpress_cnt = 0
            self.mode = (self.mode + 1) % 3 if self.mode < 3 else 0 # mode 3, 4 is unreachable
        elif bttn_val and self.prev_bttn:
            self.longpress_cnt += 1
        else: # all off
            self.longpress_cnt = 0
        self.prev_bttn = bttn_val
        sleep_ms(1) # 10ms
    
    '''
    detect mode change in the main routine
    
    there could be 2 kinds of possible mode changes.
    - mode changed by the message sent by the other ESPNow peers.
    - mode changed by the user's button.
    '''
    def detect_mode_change(self):    
        
        if self.prev_mode != self.mode:
            
            # reset the kill timer of the device
            self.mb.kill_timer = 0
            self.queen_record_flag = False # LEE   reset the flag       queen_record_flag = False # reset the flag
            
            print(f'mode {self.prev_mode} to {self.mode}')
                
            ## deinit previous timer from play mode (2)
            if self.prev_mode == 2: #LEE
                self.mb.timer.deinit()
            ##########################################
                
            self.prev_mode = self.mode
                
                
            if self.mode == 0: # idle    
                # unset LED
                self.mb.set_led_color('none')
                            
                self.mb.stop_motor() # turn off the motor
                    
                if self.mb.is_queen and len(self.mb.net_table) > 1:                
                    # multicast to slaves
                    self.mb.e.send(None, json.dumps({'tag':'idle', 'is_queen':self.mb.is_queen}))
                        
            
            if self.mode == 1: # record
                self.mb.stop_motor()
                            
                # set red LED
                self.mb.set_led_color('r')
                            
                # currently used memory index
                i = self.mb.cur_mem_idx
                            
                self.mb.duty_memories[i] = [] # reset
                self.motor_mem_cnt = 0
                    
                if len(self.mb.net_table) > 1:                
                    # multicast to slaves
                    self.queen_record_flag = True   #LEE
                    self.mb.e.send(None, json.dumps({'tag':'record', 'is_queen':True}))
                              
            if self.mode == 2: # turn on the motor
                            
                # set green LED
                self.mb.set_led_color('g')
                        
                if self.mb.is_queen and len(self.mb.net_table) > 1:
                    # multicast to peers to change the mode to 2 (play)
                    self.mb.e.send(None, json.dumps({'tag':'play',
                                                        'is_queen':self.mb.is_queen}))

                self.duty_mem_idx = 0 # reset the counter
                self.motor_update_cnt = 0
                print('duty mem : ', self.mb.duty_memories[self.mb.cur_mem_idx])
                self.mb.nSleep(True)
   
                self.p_flag = 0   #LEE
                self.mb.timer.init(period=50, mode=Timer.PERIODIC, callback=self.periodic_interrupt)
                    
                
            if self.mode == 3:
                print('mode changed to 3')
                self.mb.set_led_color('none') #temp
                # if queen (if controller)
                if self.mb.is_queen:
                    self.mb.nSleep(False)
                # if slave (if agent)
                else:
                    self.mb.nSleep(True)
                if len(self.mb.net_table) > 1:
                    # multicast to peers to change the mode to 3 (RL)
                    self.mb.e.send(None, json.dumps({'tag':'start_rl',
                                                         'is_queen':self.mb.is_queen}))
                                 
            if self.mode == 4:
                print('mode changed to 4')
                self.mb.set_led_color('y')
                self.mb.nSleep(False)
                    
            # when button is not pressed and the mode changed to 5, change the LED state.
            if self.mode == 5:
                print('mode changed to 5')
                # currently used memory index
                i = self.mb.cur_mem_idx
                self.mb.duty_memories[i] = [] # reset
                # orange
                self.mb.set_led_color('o')
                self.mb.nSleep(True)
                self.motor_mem_cnt = 0        

        
    '''
    sets the play flag every 50ms
    '''
    def periodic_interrupt(self,timer):  #LEE
        self.p_flag = 1
    
    
    '''
    utility function (bytestr -> hex / hex -> bytestr)
    '''
    
    def bytes_to_hex(self, bytestr):
        return binascii.hexlify(bytestr).decode()
        
    def hex_to_bytes(self, hexstr):
        return bytes.fromhex(hexstr)
          
    async def runner(self):
        # button/motor based interaction
        # functionalities (each task by index):
        # task 0. grouping (with the button)
        # task 1. recording 
        # task 2. playing  
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
        sleep_ms(100)
        
        self.queen_record_flag = False  #LEE
        # see if the mode was changed to recording mode by the queen
        
        # main routine
        while True:
            
            self.mb.block_power_if_idle()
                
            self.detect_mode_change() # checking when mode is changed
            
            if self.mode == 0: # idle mode
                self.button()
                # if a queen and the slave's button are both pressed within the timediff of approx. 2s
                # we define it as the 'buttons pressed at the same time'
                if self.longpress_cnt == 700:
                    print('bttn held for long time..')
                    grouping_res = grouping(self)
                    if grouping_res == -1:
                        continue
                    
                
            if self.mode == 1: # record mode
                self.button()
                await self.mb.record_motor(self.queen_record_flag)    #LEE
                if self.longpress_cnt == 700:
                    print('bttn held for long time.. do nothing')
                
            if self.mode == 2: # play mode
                # currently used memory index
                i = self.mb.cur_mem_idx
                
                if not self.mb.duty_memories[i] or (self.duty_mem_idx >= len(self.mb.duty_memories[i])): # no memory (empty)
                    self.button()
                else:
                    self.button()
                    await self.mb.async_move_motor(int(self.mb.duty_memories[i][self.duty_mem_idx]))
                    if self.longpress_cnt == 700:
                        print('bttn held for long time.. do nothing')
                    if self.p_flag == 1:      #LEE
                        self.duty_mem_idx = (self.duty_mem_idx + 1) % len(self.mb.duty_memories[i])
                        self.p_flag = 0
            
            if self.mode == 3: # RL mode
                self.button()
                if self.longpress_cnt == 700: # if longpress detected
                    await play_rl(self)
                    #if self.mb.is_queen:
                        #print(f'END:{end_state}') # send END state to serial
                
            if self.mode == 4: # upload & download mode
                # only can be aborted in the server
                self.button()
                if self.longpress_cnt == 700: # if longpress detected, start a server
                    open_server(self)

            if self.mode == 5: # record and play mode
                self.button()
                await self.mb.async_move_motor(int(self.cur_duty))
                if self.longpress_cnt == 700:
                    print('bttn held for long time.. do nothing')
                if self.motor_mem_cnt >= 30: # record and play (every 120ms)
                    self.cur_duty = self.mb.received_duty # update the duty
                self.motor_mem_cnt = (self.motor_mem_cnt + 1) % 31
                

            self.mb.kill_timer += 1
                
    # wrapper function for the runner()
    def main_runner(self):
        print('queenness : ', self.mb.is_queen)
        asyncio.run(self.runner())
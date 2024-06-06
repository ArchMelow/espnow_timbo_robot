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
from src.espnow.grouping import grouping
from src.ap.set_ap import run_APserver

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

code runner. (for comm. blocks)
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
        
        # stdin event handler (for serial communication with PC)
        self.spoll = uselect.poll()
        self.spoll.register(sys.stdin, uselect.POLLIN)
        
    
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
                    # we can now guarantee that all the members in the group are in our net table
                    # change mode from 0 to 1. (enter AP mode)
                    self.mode = 1
                    self.mb.kill_timer = 0 # reset kill timer
                    
                    self.mb.received_msg = None
                    self.mb.received_mac = None # clear the buffer
                
                

    def button(self):   #LEE
        bttn_val = self.mb.bttn.value()
        if bttn_val and not self.prev_bttn: # press
            print('bttn on')
            self.longpress_cnt = 0
        elif not bttn_val and self.prev_bttn and self.longpress_cnt < 700: # short toggle
            print('bttn off - toggled')
            self.longpress_cnt = 0
            # only mode change 2 -> 0 is available
            if self.mode == 2:
                self.mode = 0
        elif bttn_val and self.prev_bttn: # long toggle
            self.longpress_cnt += 1
        else: # all off
            self.longpress_cnt = 0
        self.prev_bttn = bttn_val
        sleep_ms(1) # check every 1ms
    
        
    '''
    utility function (bytestr -> hex / hex -> bytestr)
    '''
    
    def bytes_to_hex(self, bytestr):
        return binascii.hexlify(bytestr).decode()
        
    def hex_to_bytes(self, hexstr):
        return bytes.fromhex(hexstr)
          
    async def runner(self):
        # button based interaction
        # comm. block will be on waiting state (0) initially
        # if it is grouped with the queen, it automatically enters AP mode (1)
        # it sends its peers the payload that it has received from the app via ESPNow.
        # if the user aborts the app(sends /abort request), it will be on idle state (2)
        # if button is pressed on state 2:
        # 1) if comm. block is grouped: enter AP mode
        # 2) if comm. block is not grouped: stay on waiting state(0)
        
        
        # does not work if some queen/slave blocks are in recording mode.
        # assumes that all blocks are in either 'idle' or 'play' mode.
        
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
            
            # will have to control power usage in different way in comm blocks.
            self.mb.block_power_if_idle()
            
            if self.mode == 0: # waiting mode
                self.button()
                # if a queen and the slave's button are both pressed within the timediff of approx. 2s
                # we define it as the 'buttons pressed at the same time'
                if self.longpress_cnt == 700:
                    print('bttn held for long time..')
                    grouping_res = grouping(self)
                    if grouping_res == -1:
                        continue
                    
                
            if self.mode == 1:
                # button is not available, abort only when the app orders it to do so.
                run_APserver(self)
                self.mode = 2
                 
                            
            if self.mode == 2:
                # idle mode, just check for button press.
                self.button()
                

            self.mb.kill_timer += 1
                
    # wrapper function for the runner()
    def main_runner(self):
        print('queenness : ', self.mb.is_queen)
        asyncio.run(self.runner())
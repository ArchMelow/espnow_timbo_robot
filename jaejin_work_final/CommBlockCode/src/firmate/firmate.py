from machine import UART, Pin
from utime import sleep
import network
import espnow
import binascii
import json

PREV_LSB = 999
NO_SERIAL_CNT = 0 # global serial counter for checking if the connection is aborted.

def binstr_to_bin(bin_str):
    return int('0b' + bin_str, 2)

def check_validness(ch, net_table):
    # ch == byte meaning the command (LSB)
    # pin number should be within the table index range
    
    pin_num = int((ch >> 1) & 0b1111)
    
    return (ch >> 7) \
           and ((ch >> 6) & 0b1) \
           and ((ch >> 5) & 0b1) \
           and (pin_num > 0) \
           and (pin_num < len(net_table))



def pad_binary(binary_str):
    return '0' * (8 - len(binary_str)) + binary_str


def firmate(runner_obj):
    
    global PREV_LSB, NO_SERIAL_CNT
    
    
    # need to select which pin to use for the sensor. (currently, using d19 pin)
    # uncomment the commented code and modify 19 to other available pin numbers.
    
    # selected_pin = Pin(19, Pin.IN)
    
    while True:
        if runner_obj.mb.uart.any():
            data = runner_obj.mb.uart.read()
            NO_SERIAL_CNT = 0 # reset the counter
            
            hex_string = binascii.hexlify(data).decode()
            binary_lst = []
            hex_pairs = [hex_string[i:i+2] for i in range(0, len(hex_string), 2)]

            for hex_pair in hex_pairs:
                binary_lst.append(pad_binary(bin(int(hex_pair, 16))[2:]))
                
            # LSB is the command.
            lsb = binstr_to_bin(binary_lst[-1]) 
            
            # act (send message) only when lsb is changed && means correct action
            # option 'play', 'stop', 'record' are valid.
            if PREV_LSB != lsb and check_validness(lsb, runner_obj.mb.net_table):
                output = lsb & 0b1
                pin_num = (lsb >> 1) & 0b1111
                print(pin_num, output)
                print(PREV_LSB, lsb)
                
                # send message to motion blocks via ESPNow
                comm_str = 'play' if output == 0b1 else 'stop'
                
                runner_obj.mb.e.send(runner_obj.mb.net_table[pin_num], json.dumps({'tag':comm_str, 'is_queen':False}))
                
                PREV_LSB = lsb
                
                
                # uncomment below lines to test out inputs to Entry
                '''
                if d19_pin.value(): # HIGH
                    # send bytestring to Entry serial (Pin 5)
                    runner_obj.mb.uart.write(bytes.fromhex(hex(0b10010101)[2:]))
                    
                
                else: # LOW
                    runner_obj.mb.uart.write(bytes.fromhex(hex(0b10010100)[2:]))      
                '''
        else: # no message in the serial buffer
            if NO_SERIAL_CNT >= 50000: # if no message for 50000 loops (might have to increase this.)
                print('Entry Serial Connection Aborted.')
                return # exit

            NO_SERIAL_CNT += 1
            

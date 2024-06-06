from machine import UART
from utime import sleep
import network
import espnow
import binascii
import json

# ESPNow connection

# ESPNow setup

sta = network.WLAN(network.STA_IF)
e = espnow.ESPNow()
sta.active(True)
print(f"mac : {sta.config('mac')}")
net_table = [sta.config('mac'), b'P\x02\x91\xa3\xe1 ', b'P\x02\x91\xa3\xdb\xc4']
hex_net_table = [binascii.hexlify(m).decode() for m in net_table]
e.active(True)
e.add_peer(b'\xff' * 6) # broadcasting
for n in net_table:
    e.add_peer(n)
    
e.send(None, json.dumps({'tag':'distribute_comm', 'is_queen':False, 'net_table':hex_net_table}))


def binstr_to_bin(bin_str):
    return int('0b' + bin_str, 2)


def check_validness(ch):
    # ch == byte meaning the command (LSB)
    # port number should be within the table index range
    return (ch >> 7) \
           and ((ch >> 6) & 0b1) \
           and ((ch >> 5) & 0b1) \
           and (int((ch >> 1) & 0b1111) < len(net_table))
    
# Serial comm setup    
uart = UART(2, baudrate=9600, bits=8, parity=None, stop=1,rx=6,tx=5)

# command
prev_lsb = 999

# press reset button to start the connection with Entry
def send_msg_until_conn():
    while True:
        uart.write('Start connection')
        if uart.any():
            _ = uart.read()
            break

def pad_binary(binary_str):
    return '0' * (8 - len(binary_str)) + binary_str

send_msg_until_conn()

while True:
    if uart.any():
        data = uart.read()
        
        hex_string = binascii.hexlify(data).decode()
        binary_lst = []
        hex_pairs = [hex_string[i:i+2] for i in range(0, len(hex_string), 2)]

        for hex_pair in hex_pairs:
            binary_lst.append(pad_binary(bin(int(hex_pair, 16))[2:]))
            
        # LSB is the command.
        lsb = binstr_to_bin(binary_lst[-1]) 
        
        # act (send message) only when lsb is changed && means correct action
        # option 'play', 'stop', 'record' are valid.
        if prev_lsb != lsb and check_validness(lsb):
            output = lsb & 0b1
            pin_num = (lsb >> 1) & 0b1111
            print(pin_num, output)
            print(prev_lsb, lsb)
            
            # send message to motion blocks via ESPNow
            comm_str = 'play' if output == 0b1 else 'stop'
            
            e.send(net_table[pin_num], json.dumps({'tag':comm_str, 'is_queen':False}))
            
            prev_lsb = lsb
            
            
        
        
        

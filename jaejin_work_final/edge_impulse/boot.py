#from src.sensor import LSM9DS1
from machine import UART#, I2C
from utime import sleep_ms
import network, espnow, binascii
import json

ax,ay,az,mx,my,mz,gx,gy,gz=None,None,None,None,None,None,None,None,None
MSG, MAC = None, None



#lsm = LSM9DS1.LSM9DS1(I2C(scl=22, sda=21))
uart = UART(2, baudrate=115200, bits=8, parity=None, stop=1, rx=16, tx=17)

sta = network.WLAN(network.STA_IF)
e = espnow.ESPNow()
sta.active(True)
print(f"mac : {sta.config('mac')}")
net_table = [sta.config('mac'), b'P\x02\x91\xa3\xe14'] # replace the second entry to the motion block's MAC addr sending the sensor data
hex_net_table = [binascii.hexlify(m).decode() for m in net_table]
e.active(True)
e.add_peer(b'\xff' * 6) # broadcasting
for n in net_table:
    e.add_peer(n)
    
e.send(None, json.dumps({'tag':'distribute', 'is_queen':True, 'net_table':hex_net_table}))

'''
ESPNow callback function for the slaves
'''
def recv_cb_slave(e):
    global ax,ay,az,mx,my,mz,gx,gy,gz
    
    while True:
        mac,msg = e.irecv(0)
        if msg is None:
            break    
        
        #print(f'received {msg} from the callback')
        MSG = bytes(msg.decode().replace('\x00', '').encode('utf-8'))
        MAC = mac
        json_msg = json.loads(MSG)
        
        #print(json_msg['tag'])
        if json_msg['tag'] == 'to_comm':
            ax, ay, az = json_msg['ax'], json_msg['ay'], json_msg['az']
            mx, my, mz = json_msg['mx'], json_msg['my'], json_msg['mz']
            gx, gy, gz = json_msg['gx'], json_msg['gy'], json_msg['gz']
            
            #print(f'babab : {ax},{ay},{az}')
        
        MSG = None
        MAC = None # clear the buffer


e.irq(recv_cb_slave)




while True:
    
    sleep_ms(100)
    tof_list = [ax,ay,az,gx]
    print(tof_list)
    if None not in tof_list:
        rounded_list = [round(t, 3) for t in tof_list]
        x = list(map(str, rounded_list))
        uart.write(','.join(x) + '\n')
        sleep_ms(500)


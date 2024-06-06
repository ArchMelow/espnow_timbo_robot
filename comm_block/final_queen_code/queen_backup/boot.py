# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
import machine
from machine import Pin
from utime import sleep_ms
import os
import network
import binascii
import socket
import re
import json
import gc # garbage collection
import micropython

print('boot start')

# global LED Pin
led_red = Pin(19, Pin.OUT)
led_green = Pin(20, Pin.OUT)


def free_sta(sta_if):
    sta_if.disconnect()
    sta_if.active(False)
    sta_if = None


def boot_with_update():
    # only if the setting file does not exist
    if 'wifi.conf' not in os.listdir('./conf'):
        ssid, pwd = configure_wifi()
        json_dict = dict()
        json_dict['ssid'] = ssid
        json_dict['pwd'] = pwd
        with open('./conf/wifi.conf', 'w') as f:
            f.write(json.dumps(json_dict))
    
    # if wifi config exists
    else:
        sta_if = network.WLAN(network.STA_IF)
        if not sta_if.isconnected():
            print('connecting to network in the configuration...')
            sta_if.active(True)
            
            scanned = sta_if.scan()
            #print('scanned : ', scanned)


            # read from the conf (file exists)
            with open('./conf/wifi.conf', 'r') as f:
                read_data = f.read()
                print(read_data)
                wifi_conf = json.loads(read_data)
                            
            if not wifi_conf:
                return
            
            print(wifi_conf)
            
            # check if ssid is in the scanned list.
            # if not, reconfigure wifi. (AP changed)
            ssids = [tup[0].decode('utf-8') for tup in scanned]
            if wifi_conf['ssid'] not in ssids:
                ssid, pwd = configure_wifi()
                json_dict = dict()
                json_dict['ssid'] = ssid
                json_dict['pwd'] = pwd
                with open('./conf/wifi.conf', 'w') as f:
                    f.write(json.dumps(json_dict))
                return
                
                
            # check if there was an update.
            # if there is temp.py in ./main_program, rename it to main.py
            # TODO: only updates the main.py file, but should be replaced with the part
            # where all the folders are updated via a .zip archive or something.
            if 'temp.py' in os.listdir('./main_program'):
                # remove main.py in the folder
                os.remove('./main_program/main.py')
                print('upgrading main.py to a new version..')
                os.rename('./main_program/temp.py', './main_program/main.py')
                print('finished update.')
        
        
        free_sta(sta_if)
                
        


# reset wifi settings and start over
def del_wifi_conf():
    if 'wifi.conf' in os.listdir('./conf'):
        os.remove('./conf/wifi.conf')

def web_page(access_ip_str = ""):
    html_page = '''
                <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>WiFi Configuration</title>
        </head>
        <body>

            <h2>WiFi Configuration</h2>

            <form action="#" method="post" id="wifiForm" enctype = "text/plain">
                <label for="ssid">SSID:</label>
                <input type="text" id="ssid" name="ssid" required><br>

                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required><br>

                <input type="submit" value="Submit">
            </form>
            <br><br>
            
            <form action="/end" method="post">
                <input type="submit" value="end">
            </form>
            
            <br><br>
            <pre>{access_ip_str}</pre>
            
        </body>
        </html>

    '''.format(access_ip_str = access_ip_str)
    return html_page
    
def configure_wifi():
    # start connection (AP mode)
    ap = network.WLAN(network.AP_IF)
    
    # unique MAC addr to create a unique AP ssid
    hex_mac = binascii.hexlify(ap.config('mac')).decode()
    ap_ssid = f"timbo-AP-{hex_mac}"
    # add a passwd here (optional)
    
    # activate the AP
    ap.active(True)
    ap.config(essid = ap_ssid)
    
    print(f'timbo AP started as {ap_ssid}')
    print(ap.ifconfig())
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(1) # only one device accessible
    
    # server listening
    
    ssid_value = None; password_value = None
    access_ip_str = ""; ip = None
    
    while True:
    
    
        conn, addr = s.accept()
        print("Got connection from %s" % str(addr))
        
    
        # Socket receive()
        request=conn.recv(1024)
        
        # Socket send()
        
        request = request.decode()
        st = " ".join([r.strip('\r').rstrip().lstrip() for r in request.split('\n')])
        print(st)
        
    
        ssid_pattern = re.compile(r'ssid=([^\s]+)')
        password_pattern = re.compile(r'password=([^\s]+)')

        ssid_match = ssid_pattern.search(request)
        password_match = password_pattern.search(request)

        # end the server.
        if request.find('end') != -1:
            break


        if ssid_match and password_match:
            ssid_value = ssid_match.group(1)
            password_value = password_match.group(1)

            print("SSID:", ssid_value)
            print("Password:", password_value)
            # attempt to connect for a while
            sta_if = network.WLAN(network.STA_IF)
            if sta_if.active():
                sta_if.disconnect()
                sta_if.active(False)
            
            sta_if.active(True)
            sta_if.connect(ssid_value, password_value)
            while sta_if.isconnected():
                pass
            # for the connection to settle to retrieve IP, this is necessary!
            ipconf = sta_if.ifconfig()
            while ipconf and ipconf[0] == '0.0.0.0':
                ipconf = sta_if.ifconfig()
                sleep_ms(100) # sleep every 100ms
            print(ipconf)    
                
            if ipconf:
                ip = ipconf[0]
            sta_if.disconnect()
            sta_if.active(False)
            sta_if = None
            
            if ip:
                access_addr = ip + ':80'
                print(access_addr)
                access_ip_str = f"By long pressing your button on mode 3, reach this server at {access_addr}"
            
        else:
            print("SSID or Password not found in the provided data.")
            
        response = web_page(access_ip_str)
        conn.send('HTTP/1.1 200 OK\n')
        conn.send('Content-Type: text/html\n')
        conn.send('Connection: close\n')
        conn.sendall(response)
    
        # got the ssid and the password
        conn.close()
    
    # deactivate socket and AP
    conn = None
    ap.active(False)

    
    return ssid_value, password_value
    
    
'''
main part.
'''
    
# sleep 4s for the debugging (need to enable CTRL+C to escape the program in IDE)
sleep_ms(4000)
led_red.value(1); led_green.value(0)
#micropython.kbd_intr(-1)    
    
#boot_with_update()

with open('./conf/is_queen.conf', 'r') as f:
    data_read = f.read()
    print(data_read)
    queenness = True if data_read.strip() == 'True' else False

from main_program.main import Runner # we have to check if there was an upgrade / downgrade.

r = Runner(queenness)
r.main_runner()
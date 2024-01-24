# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
import machine
from main_program.main import Runner
import os
import network
import binascii
import socket
import re
import json
import app
import gc # garbage collection
from app.ota_updater import OTAUpdater


print('boot start')


def boot_with_update():
    # only if the setting file does not exist
    if 'wifi.conf' not in os.listdir('./wifi'):
        ssid, pwd = configure_wifi()
        json_dict = dict()
        json_dict['ssid'] = ssid
        json_dict['pwd'] = pwd
        with open('./wifi/wifi.conf', 'w') as f:
            f.write(json.dumps(json_dict))
    
    # if wifi config exists
    else:
        sta_if = network.WLAN(network.STA_IF)
        if not sta_if.isconnected():
            print('connecting to network in the configuration...')
            sta_if.active(True)
            

            # read from the conf (file exists)
            with open('./wifi/wifi.conf', 'r') as f:
                read_data = f.read()
                print(read_data)
                wifi_conf = json.loads(read_data)
                            
            if not wifi_conf:
                return
            
            print(wifi_conf)
            sta_if.connect(wifi_conf['ssid'],
                           wifi_conf['pwd'])
            
            print('Connecting...')
            while not sta_if.isconnected():
                pass
        
        ota_updater = OTAUpdater('https://github.com/ArchMelow/espnow_timbo_robot',
                                 main_dir = 'main_program')
        has_updated = ota_updater.install_update_if_available()
        if has_updated:
            machine.reset()
        else:
            del(ota_updater)
            gc.collect()
            
            
        


# reset wifi settings and start over
def del_wifi_conf():
    if 'wifi.conf' in os.listdir('./wifi'):
        os.remove('./wifi/wifi.conf')

def web_page():
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

        </body>
        </html>

    '''
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
    
    while ssid_value is None and password_value is None:
    
    
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

        # Use the regular expressions to extract values
        ssid_match = ssid_pattern.search(request)
        password_match = password_pattern.search(request)

        # Check if matches are found
        if ssid_match and password_match:
            ssid_value = ssid_match.group(1)
            password_value = password_match.group(1)

            print("SSID:", ssid_value)
            print("Password:", password_value)
        else:
            print("SSID or Password not found in the provided data.")
            
        response = web_page()
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
    
    
boot_with_update()

with open('is_queen.conf', 'r') as f:
    data_read = f.read()
    queenness = True if data_read == 'True' else False

r = Runner(is_queen=queenness)
r.main_runner()



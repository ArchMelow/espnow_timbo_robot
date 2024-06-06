from utime import sleep_ms
import os
import network
import binascii
import socket
import re
import json
import gc # garbage collection
import micropython


def generate_table(net_table=None):
    assert net_table[1:] # net table must not be empty
    
    returned_str = ""
    for m in net_table[1:]:
        hex_m = binascii.hexlify(m).decode()
        returned_str += '''<tr>
                <td>Timbo_{hex_m}</td>
                <td>
                    <form action="#" method="POST">
                        <input type="hidden" name="device" value=Timbo_{hex_m}>
                        <input type="hidden" name="button" value="PLAY">
                        <button type="submit" class="button">PLAY</button>
                    </form>
                </td>
                <td>
                    <form action="#" method="POST">
                        <input type="hidden" name="device" value="Timbo_{hex_m}">
                        <input type="hidden" name="button" value="STOP">
                        <button type="submit" class="button">STOP</button>
                    </form>
                </td>
            </tr>'''.format(hex_m=hex_m)
    
    return returned_str
        


def web_page(access_ip_str = "", net_table = None):
    
    generated_str = generate_table(net_table)
    
    html_page = '''<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Timbo Device List</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }}
                form {{
                    width: 300px;
                    height: 50px;
                    background-color: gold;
                    color: white;
                }}
                
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    border: 1px solid #dddddd;
                    text-align: left;
                    padding: 8px;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .button {{
                    padding: 5px 10px;
                    color: white;
                    background-color: #007bff;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    text-decoration: none;
                    font-size: 14px;
                }}
                .button:hover {{
                    background-color: #0056b3;
                }}
            </style>
        </head>
        <body>

        <h2>Timbo Device List</h2>

        <table>
            <tr>
                <th>Device</th>
                <th>Play</th>
                <th>Stop</th>
            </tr>
            
            {generated_str}
        </table>

        </body>
        </html>
        '''.format(generated_str=generated_str)
    return html_page
    
def run_APserver(runner_obj):
    # start connection (AP mode)
    ap = network.WLAN(network.AP_IF)
    
    # unique MAC addr to create a unique AP ssid
    hex_mac = binascii.hexlify(ap.config('mac')).decode()
    ap_ssid = f"timbo-AP-{hex_mac}"
    
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
        

        # end the server.
        if request.find('end') != -1:
            break
        
        comm = ''
        try:
            comm = st.split(' ')[-1].strip()
            device_mac = bytes.fromhex(comm.split('_')[-1].split('&')[0])
            action = comm.split('=')[-1].strip()
        except Exception as msg_e:
            print(f'Exception occurred : {msg_e}')
        
        print(f'mac : {device_mac}, action : {action}')
        
        # PLAY for specific device
        if device_mac and action == 'PLAY':
            runner_obj.mb.e.send(device_mac, json.dumps({'tag':'play',
                                                        'is_queen':runner_obj.mb.is_queen}))
        
        if device_mac and action == 'STOP':
            runner_obj.mb.e.send(device_mac, json.dumps({'tag':'stop',
                                                         'is_queen':runner_obj.mb.is_queen}))
        
        
        response = web_page(access_ip_str, runner_obj.mb.net_table)
        conn.send('HTTP/1.1 200 OK\n')
        conn.send('Content-Type: text/html\n')
        conn.send('Connection: close\n')
        conn.sendall(response)
    
        # got the ssid and the password
        conn.close()
    
    # deactivate socket and AP
    conn = None
    ap.active(False)


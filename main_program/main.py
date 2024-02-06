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
import socket
import gc

'''
TODO :

- load network table from file
- save network table to file
- load motor data from file 
- download motor data from the https server (mode 3)
- add OTA update functionality to the https server (mode 3)

'''


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
        self.led_red = PWM(Pin(19, Pin.OUT))
        self.led_green = PWM(Pin(20, Pin.OUT))
        self.led_red.freq(1000)
        self.led_green.freq(1000)
        self.set_led_color('none') # defaults to mode 0
        
        self.which_led = 0
        self.bttn = Pin(35, Pin.IN, Pin.PULL_UP)
        self.backward_motor = Pin(33, Pin.OUT)
        self.forward_motor = Pin(32, Pin.OUT)
        self.nSleep = Pin(7, Pin.OUT)
        self.adc = ADC(Pin(36), atten=ADC.ATTN_6DB) # analog-to-digital conversion on Pin 36
        self.dummy_pin = Pin(27, Pin.OUT)
        self.callback_pin = Pin(26, Pin.OUT)
        self.mac_addr = None
        
        # PWM instances, PWM duty value 
        self.backward_pwm = PWM(self.backward_motor, freq = 10000)
        self.forward_pwm = PWM(self.forward_motor, freq = 10000)
        self.duty_cycle = 0
        self.prev_duty_error = 0
        
        # motor duty memory (empty) - could cause memory overflow
        # now maintains 5 memory arrays, could be chosen with the command via the download mode from the queen (mode 3)
        #self.duty_memory = []
        self.duty_memories = [[] for _ in range(5)]
        self.cur_mem_idx = 0 # currently used memory index (defaults to 0)
        self.duty_mem_limit = 100000 # memory limit for each duty memory array.
        self.mem_counter = 0
        self.recorded_adc = 0
        
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
        
        
        self.timer = Timer(1)  #LEE
        
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
        asyncio.sleep(0.000001) # 0.01 ms
    
    def sync_move_motor(self, cur_value):
        self.move_motor(cur_value)
        sleep_ms(1)
       
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
        
        
        
    async def record_motor(self):
        # overwrite (until the memory is full)
        adc = self.adc.read()
        # index for the currently used memory index
        i = self.cur_mem_idx
        print(i)
        # for every cycle
        # if current read adc value diff is larger than 10 compared to the previous adc, add to mem
        if (len(self.duty_memories[i]) < self.duty_mem_limit):
            if self.mem_counter == 45 and abs(self.prev_rec - adc) < 3500:
                self.duty_memories[i].append(adc)
                if self.is_queen and len(self.net_table) > 1: # if this is queen in the record mode, send the duty value to the group
                    # takes approx. 2.5ms to send
                    self.e.send(None, json.dumps({'tag':'duty',
                                                      'is_queen':True,
                                                      'val':adc}))
                    
                
            self.prev_rec = adc
            self.mem_counter = (self.mem_counter + 1) % 46 # increment counter
    
    
    # save motor data as a file (duty.dat)
    def save_motor_data(self):
        # simply overwrite
        with open('./motor_data/duty.dat', 'w') as f:
            for lst in self.duty_memories:
                for i, d in enumerate(lst):
                    f.write(d)
                    if i < len(lst) - 1:
                        f.write(',')
                f.write('\n') # add newline
            
        
    
    
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
        # record and play at the same time. (mode 4)
        self.motor_mem_cnt = 0
        self.cur_duty = 0
        # play flag (play memory every 40ms timer tick)
        self.p_flag = 0  #LEE
        
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
                self.prev_mode = 2 # prevent the msg ('play') sent from this device
                
                # set green LED
                self.mb.set_led_color('g')
                
                self.duty_mem_idx = 0 # reset the counter
                self.motor_update_cnt = 0
                self.mb.nSleep(True)
                
                # set timer for playing recorded memory
                self.p_flag = 0   #LEE
                self.mb.timer.init(period=40, mode=Timer.PERIODIC, callback=self.periodic_interrupt)
                
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer
            
            if json_msg['tag'] == 'idle':
                self.mode = 0
                self.mb.received_msg = None
                self.mb.received_mac = None
     

    def recv_cb_slave(self, e):
        while True:
            mac,msg = e.irecv(0)
            if msg is None:
                break    
            self.mb.callback_pin.value(1)
            print(f'received {msg} from the callback')
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
                    self.mode = 4 # change mode to 4
                    self.mb.received_msg = None
                    self.mb.received_mac = None
                if json_msg['tag'] == 'duty':
                    self.mb.received_duty = int(json_msg['val']) # save the duty sent from the queen (some values could be ignored by the slave!)
                    # currently used memory index
                    i = self.mb.cur_mem_idx
                    self.mb.duty_memories[i].append(self.mb.received_duty)
                    self.mb.received_msg = None
                    self.mb.received_mac = None # clear the buffer
                if json_msg['tag'] == 'idle':
                    self.mode = 0
                    self.mb.received_msg = None
                    self.mb.received_mac = None
 
            
            if json_msg['tag'] == 'play':
                    
                self.mode = 2 # job done
                self.prev_mode = 2 # prevent the msg ('play') sent from this device
                
                # set green LED
                self.mb.set_led_color('g')
                                               
                self.duty_mem_idx = 0 # reset the counter
                self.motor_update_cnt = 0
                self.mb.nSleep(True)
            
                # set timer for playing recorded memory
                self.p_flag = 0   #LEE
                self.mb.timer.init(period=40, mode=Timer.PERIODIC, callback=self.periodic_interrupt)
                    
                self.mb.received_msg = None
                self.mb.received_mac = None # clear the buffer

               
    
    async def button(self):
        bttn_val = self.mb.bttn.value()
        if not bttn_val and self.prev_bttn:
            print('bttn on')
            self.longpress_cnt = 0
        elif bttn_val and not self.prev_bttn and self.longpress_cnt < 700:
            print('bttn off - toggled')
            self.longpress_cnt = 0
            if self.mb.is_queen:
                self.mode = (self.mode + 1) % 4 if self.mode < 4 else 0 # mode 4 is unreachable
            else:
                self.mode = (self.mode + 1) % 3 if self.mode < 3 else 0 # mode 3, 4 is unreachable
        elif not bttn_val and not self.prev_bttn:
            self.longpress_cnt += 1
        else: # all off
            self.longpress_cnt = 0
        self.prev_bttn = bttn_val
        sleep_ms(1) # 10ms
        
    
    def periodic_interrupt(self,timer):  #LEE
        self.p_flag = 1
    
    
    def web_page(self,file_contents=""):
    
        mem = ["1,2,3,4,5","2,3,4","6,5,4","3,6,8,4","2,5,8,5"]
        
        
        html_page = """<!DOCTYPE html>
        <html>
        <head>
            <title>File Upload</title>
            <script>
                function downloadFile(content, fileName) {{
                    var blob = new Blob([content], {{ type: 'text/plain' }});
                    var link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);
                    link.download = fileName;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }}
            </script>
        </head>
        <body>
            <h2>Select a file to upload:</h2>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file">
                <br><br>
                <input type="submit" value="Upload and Display">
            </form>
            <br><br>
            <h3>End Server</h3>
            <form action="/end" method="post">
                <input type="submit" value="end">
            </form>
            <br><br>
            <h3>Change save slot</h3>
            <form action="/slots" method="post">
                <input type="submit" name="motor_1" value="1">
                <input type="submit" name="motor_2" value="2">
                <input type="submit" name="motor_3" value="3">
                <input type="submit" name="motor_4" value="4">
                <input type="submit" name="motor_5" value="5">
            </form>
            <br><br>
            <h3>Download Motor Memory</h3>
            <form action="/download_motor" method="post">
                <input type="button" onclick="downloadFile('1,2,3,4,5', 'file1.txt')" value="mem 1">
                <input type="button" onclick="downloadFile('2,3,4', 'file2.txt')" value="mem 2">
                <input type="button" onclick="downloadFile('6,5,4', 'file3.txt')" value="mem 3">
                <input type="button" onclick="downloadFile('3,6,8,4', 'file4.txt')" value="mem 4">
                <input type="button" onclick="downloadFile('2,5,8,5', 'file5.txt')" value="mem 5">
            </form>
            <br>
            <br>
            <h3>File Contents:</h3>
            <pre>{file_contents}</pre>
        </body>
        </html>
        """.format(file_contents=file_contents)
        
        return html_page


    
    
    def open_server(self):
        
        print('bttn held for long time.. open server')
        
        # read from the conf (file exists)
        with open('../wifi/wifi.conf', 'r') as f:
            read_data = f.read()
            print(read_data)
            wifi_conf = json.loads(read_data)
                            
        if not wifi_conf:
            return
            
        print(wifi_conf)
        self.mb.sta.connect(wifi_conf['ssid'],
                        wifi_conf['pwd'])
            
        print('Connecting...')
        print(f'{self.mb.sta.active()}')
        while not self.mb.sta.isconnected():
            #print(f'status : {self.mb.sta.status()}')
            pass
        
        # open a socket server
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        
        print(self.mb.sta.ifconfig())
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(addr)
        s.listen(1)  # only one device accessible

        end_flag = False

        while not end_flag:
            conn, addr = s.accept()
            print("Got connection from %s" % str(addr))

            
            cl_file = conn.makefile('rwb', 0)

            # if the parsing for the request is done correctly,
            # all the other formats can be downloaded.

            request = b""
            while True:
                line = cl_file.readline()
                if not line or line == b'\r\n':
                    break
                request += line
            
            if request:
                method, path, *_ = request.decode().split('\r\n')[0].split(' ')

            #print(request)

            if method == 'POST' and path == '/end':
                end_flag = True
                conn.close()
                conn = None
                self.mb.sta.disconnect()
                self.mb.sta.active(False)
                sleep_ms(1000)
                self.mb.sta.active(True)
                gc.collect()
                break
                
            if method == 'POST' and path == '/slots':
                content_length = 0
                
                for line in request.decode().split('\r\n'):
                    if line.startswith('Content-Length: '):
                        content_length = int(line.split(' ')[1])
                        break
                    
                form_data = cl_file.read(content_length).decode()
                print(form_data)

                for item in form_data.split('&'):
                    k, v = item.split('=')
                    self.mb.cur_mem_idx = int(v)

                print(f'save slot changed to {self.mb.cur_mem_idx}')
                response = self.web_page()

            if method == 'POST' and path == '/upload':
                
                content_length = 0
                for line in request.decode().split('\r\n'):
                    if line.startswith('Content-Length: '):
                        content_length = int(line.split(' ')[1])
                        break

                print(content_length)

                s1 = cl_file.readline() # FIRST LINE
                s2 = cl_file.readline() # SECOND LINE
                filename = s2.decode().split(';')[-1].split('=')[-1]
                filename = filename[1:-3].strip()
                print('filename : ', filename)

                if not filename:
                    print('no file to upload.')
                    continue
                
                
                # MUST HANDLE THE CASE WHERE STREAM IS EMPTY(FILENAME CANNOT BE FETCHED)
                with open(filename, 'wb') as f:
                    write_cnt = 0
                    # read first four lines.
                    
                    s3 = cl_file.readline() # THIRD LINE
                    s4 = cl_file.readline() # FOURTH LINE
                    print(s1, s2, s3, s4)
                    write_cnt += (len(s1) + len(s2) + len(s3) + len(s4))
                    if s3.decode().split(':')[-1].strip() == 'text/plain':
                        print('plain text file downloading.')
                    
                    while True:
                        line = cl_file.readline()
                        if line[6:24] == b'WebKitFormBoundary':
                            break
                        f.write(line)
                    
                
                # Extract the file content from the POST data
                with open(filename, 'rb') as f:
                    if os.stat(filename)[6] < 5000: # if size is more than 5000b, do not display
                        if os.stat(filename)[6] == 2: # empty ('\r\n')
                            file_content = "file empty."
                        else:
                            file_content = f.read().decode() # decode, assuming this is binary file.
                    else:
                        file_content = "file size too large to display here."
                

                response = self.web_page(file_contents=file_content)
            else:
                response = self.web_page()
            

            # Send the HTTP response
            conn.sendall('HTTP/1.1 200 OK\n')
            conn.sendall('Content-Type: text/html\n')
            conn.sendall('Connection: close\n')
            conn.sendall('\n')
            conn.sendall(response)

            conn.close()
        
            
            
        
                    
    
    
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
        
        # main routine
        while True:
            
            ########## checking when mode is changed  #######################################
            
            if self.prev_mode != self.mode:
            
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
                    
                    if len(self.mb.net_table) > 1:                
                        #await asyncio.sleep_ms(100)
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
                    
                    # if this is the queen
                    if self.mb.is_queen:
                        # only if the net table is not empty
                        if len(self.mb.net_table) > 1:                
                            #await asyncio.sleep_ms(100)
                            # multicast to slaves
                            self.mb.e.send(None, json.dumps({'tag':'record', 'is_queen':True}))
                              
                
                if self.mode == 2: # turn on the motor
                            
                    # set green LED
                    self.mb.set_led_color('g')
                        
                    if len(self.mb.net_table) > 1:
                        # multicast to peers to change the mode to 2 (play)
                        #self.mb.dummy_pin.value(1) # how many time send?
                        self.mb.e.send(None, json.dumps({'tag':'play',
                                                        'is_queen':self.mb.is_queen}))
                        #self.mb.dummy_pin.value(0)
                    
                    self.duty_mem_idx = 0 # reset the counter
                    self.motor_update_cnt = 0
                    print('duty mem : ', self.mb.duty_memories[self.mb.cur_mem_idx])
                    self.mb.nSleep(True)
   
                    self.p_flag = 0   #LEE
                    self.mb.timer.init(period=40, mode=Timer.PERIODIC, callback=self.periodic_interrupt)
                    
                    
                # when button is not pressed and the mode changed to 3, change the LED state.
                if self.mode == 4:
                    print('mode changed to 4')
                    # currently used memory index
                    i = self.mb.cur_mem_idx
                    self.mb.duty_memories[i] = [] # reset
                    # orange
                    self.mb.set_led_color('o')
                    self.mb.nSleep(True)
                    self.motor_mem_cnt = 0
                
            ##################################################################################
            
            if self.mode == 0: # idle mode
                #tasks = [self.button()]
                #res = await asyncio.gather(*tasks)
                await self.button()
                # if a queen and the slave's button are both pressed within the timediff of approx. 2s
                # we define it as the 'buttons pressed at the same time'
                if self.longpress_cnt == 700:
                    print('bttn held for long time..')
                    
                    # correct grouping based on callback
                    if self.mb.is_queen:
                        
                        
                        sleep_ms(1500) # wait 1.5s (listen)
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
                        sleep_ms(3500) # wait 3.5s (expect button async)
                        
                        # if no received message, queen was not pressed at the same time (approx.).
                        if self.mb.received_msg is None:
                            pass # do nothing
                        
                        else:
                            # assume we received the msg
                            msg_obj = json.loads(self.mb.received_msg)
                            
                            # ignore slaves' messages
                            if not msg_obj['is_queen']:
                                continue
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
                await self.button()
                await self.mb.record_motor()
                if self.longpress_cnt == 700:
                    print('bttn held for long time.. do nothing')
                
            if self.mode == 2: # play mode
                # currently used memory index
                i = self.mb.cur_mem_idx
                
                if not self.mb.duty_memories[i] or (self.duty_mem_idx >= len(self.mb.duty_memories[i])): # no memory (empty)
                    await self.button()
                else:
                    await self.button()
                    await self.mb.async_move_motor(int(self.mb.duty_memories[i][self.duty_mem_idx]))
                    if self.longpress_cnt == 700:
                        print('bttn held for long time.. do nothing')
                    if self.p_flag == 1:      #LEE
                        self.duty_mem_idx = (self.duty_mem_idx + 1) % len(self.mb.duty_memories[i])
                        self.p_flag = 0
                
                
            if self.mode == 3: # upload & download mode
                # only can be aborted in the server
                await self.button()
                if self.longpress_cnt == 700: # if longpress detected, start a server
                    self.open_server()

            if self.mode == 4: # record and play mode
                await self.button()
                await self.mb.async_move_motor(int(self.cur_duty))
                #print('duty ', int(self.cur_duty))
                if self.longpress_cnt == 700:
                    print('bttn held for long time.. do nothing')
                if self.motor_mem_cnt >= 45: # record and play (every 45ms)
                    self.cur_duty = self.mb.received_duty # update the duty
                self.motor_mem_cnt = (self.motor_mem_cnt + 1) % 46
                
                
                
                
                '''
                self.mb.sta.active(False)
                sleep_ms(1000)
                self.mb.sta.active(True) # this doesn't matter
                '''
                
          
    # wrapper function for the runner()
    def main_runner(self):
        print('queenness : ', self.mb.is_queen)
        asyncio.run(self.runner())

import json, socket, os
from machine import reset
from utime import sleep_ms
import gc

'''
with the Runner object, open a websocket server with a web page  
'''

def web_page(runner_obj,file_contents=""):
    
    mem = []
    for arr in runner_obj.mb.duty_memories:
        if arr:
            joined_arr = '\'' + ','.join([str(a) for a in arr]) + '\''
        else:
            joined_arr = '\'empty\'' # empty string
        mem.append(joined_arr)
    print(mem)
        
    html_page = f"""<!DOCTYPE html>
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
        <h3>OTA Updater</h3>
        <br><br>
        <b>main program updater</b>
        <p>select the main.py file you wish to install on the device.</p>
        <form action="/update" method="post" enctype="multipart/form-data">
            <input type="file" name="file">
            <br><br>
            <input type="submit" value="update main program">
        </form>
        <br><br>
        <b>model updater</b>
        <p>select a model, and the model will be automatically uploaded to the device.</p>
        <form action="/model" method="post" enctype="multipart/form-data">
            <input type="file" name="file">
            <br><br>
            <input type="submit" value="update model">
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
            <input type="button" onclick="downloadFile({mem[0]}, 'file1.txt')" value="mem 1">
            <input type="button" onclick="downloadFile({mem[1]}, 'file2.txt')" value="mem 2">
            <input type="button" onclick="downloadFile({mem[2]}, 'file3.txt')" value="mem 3">
            <input type="button" onclick="downloadFile({mem[3]}, 'file4.txt')" value="mem 4">
            <input type="button" onclick="downloadFile({mem[4]}, 'file5.txt')" value="mem 5">
        </form>
        <br>
        <br>
        <h3>File Contents:</h3>
        <pre>{file_contents}</pre>
    </body>
    </html>
    """
        
    return html_page


    
    
def open_server(runner_obj):
        
    print('bttn held for long time.. open server')
        
    print('cwd : ', os.getcwd())
    # read from the conf (file exists)
    with open('../conf/wifi.conf', 'r') as f:
        read_data = f.read()
        print(read_data)
        wifi_conf = json.loads(read_data)
                            
    if not wifi_conf:
        return
            
    print(wifi_conf)
    runner_obj.mb.sta.connect(wifi_conf['ssid'],
                    wifi_conf['pwd'])
            
    print('Connecting...')
    print(f'{runner_obj.mb.sta.active()}')
    while not runner_obj.mb.sta.isconnected():
        #print(f'status : {runner_obj.mb.sta.status()}')
        pass
        
    # open a socket server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        
    print(runner_obj.mb.sta.ifconfig())
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)  # only one device accessible

    end_flag = False

    while True:
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
            conn.close()
            conn = None
            runner_obj.mb.sta.disconnect()
            runner_obj.mb.sta.active(False)
            sleep_ms(1000)
            runner_obj.mb.sta.active(True)
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
                runner_obj.mb.cur_mem_idx = int(v)

            print(f'save slot changed to {runner_obj.mb.cur_mem_idx}')
            response = web_page(runner_obj)

        if (method == 'POST' and path == '/upload') or \
            (method == 'POST' and path == '/update'):
                
            content_length = 0
            for line in request.decode().split('\r\n'):
                if line.startswith('Content-Length: '):
                    content_length = int(line.split(' ')[1])
                    break

            print(content_length)

            s1 = cl_file.readline() # FIRST LINE
            s2 = cl_file.readline() # SECOND LINE
                
            if path == '/upload':
                filename = s2.decode().split(';')[-1].split('=')[-1]
                filename = filename[1:-3].strip()
            if path == '/update': # update main.py
                filename = './main_program/temp.py'
                    
            print('filename : ', filename)

            # MUST HANDLE THE CASE WHERE STREAM IS EMPTY(FILENAME CANNOT BE FETCHED)
            if not filename:
                print('no file to upload.')
                continue
                
            with open(filename, 'wb') as f:
                write_cnt = 0
                # read first four lines.
                    
                s3 = cl_file.readline() # THIRD LINE
                s4 = cl_file.readline() # FOURTH LINE
            
                write_cnt += (len(s1) + len(s2) + len(s3) + len(s4))
                if s3.decode().split(':')[-1].strip() == 'text/plain':
                    print('plain text file downloading.')
                    
                while True:
                    line = cl_file.readline()
                    if line[6:24] == b'WebKitFormBoundary':
                        break
                    f.write(line)
                        
            # finished update (main.py), reset the machine in this case.
            if path == '/update':
                conn.close()
                conn = None
                runner_obj.mb.sta.disconnect()
                runner_obj.mb.sta.active(False)
                sleep_ms(1000)
                runner_obj.mb.sta.active(True)
                gc.collect()
                reset()
                    
                
            # Extract the file content from the POST data
            with open(filename, 'rb') as f:
                if os.stat(filename)[6] < 5000: # if size is more than 5000b, do not display
                    if os.stat(filename)[6] == 2: # empty ('\r\n')
                        file_content = "file empty."
                    else:
                        file_content = f.read().decode() # decode, assuming this is binary file.
                else:
                    file_content = "file size too large to display here."
                

            response = web_page(runner_obj, file_contents=file_content)
        else:
            response = web_page(runner_obj)
            

        # Send the HTTP response
        conn.sendall('HTTP/1.1 200 OK\n')
        conn.sendall('Content-Type: text/html\n')
        conn.sendall('Connection: close\n')
        conn.sendall('\n')
        conn.sendall(response)

        conn.close()

from src.sensor import LSM9DS1
from machine import I2C
import micropython
import json
import sys

async def play_rl(runner_obj):
        
    '''
    train 2 slaves to walk a reindeer-like assembled robot
    serial comm. -> do not print out anything unnecessary!
    '''
    lsm = None # init
    sl = [] # init
        
    #print('enter rl')
        
    if runner_obj.mb.is_queen:               
        if len(runner_obj.mb.net_table) != 3:
            return -1 # failure
        for m in runner_obj.mb.net_table:
            i = runner_obj.bytes_to_hex(m)
            runner_obj.recv_flags[i] = False # init flags
        sl = list(runner_obj.recv_flags.keys()) # slave mac addrs
        # fix the order of the slave mac addrs
        sl = sorted(sl) # return this later
            
    else: # slave
        lsm = LSM9DS1.LSM9DS1(I2C(scl=22, sda=21))
        
        
    while True:
            
        if runner_obj.mb.is_queen: # controller
            cnt = 0
            cycle_cnt = 0
            '''
            <steps>
            1. receive action from the PC (serial)
            2. broadcast the action data to the slaves
            check the following:
            - There are exactly two slaves with the corresponding roles (head and tail)
            - They are grouped to this queen.
            3. wait until all the slaves' results are received. (block)
            4. merge the results received and send it to the PC (serial)
            '''
                
                
            #print('enter while loop')
                
            while not runner_obj.spoll.poll(0):
                #cycle_cnt = (cycle_cnt + 1) % 100001
                #if cycle_cnt == 1000:
                    #cycle_cnt = 0
                    #cnt += 1
                runner_obj.mb.set_led_color('g')
                #print('hanging..')
                pass # hang until message arrives
                
            runner_obj.mb.set_led_color('o')
            micropython.kbd_intr(3) # restore
                
            #reset()
                
            f = open('log.txt', 'w')
            f.write('out of loop !')
                
        
            # process a line from the serial (step 1)
            buf = b''
                
            #stdin_flushed = sys.stdin.flush()

            while runner_obj.spoll.poll(0):
                this = sys.stdin.read(1)
                if not this:
                    break
                buf += this
            buf = buf.decode('utf-8')
                
            '''
            if buf:
                #print(buf)
                f.write(buf)
                f.close()
            '''
                
            # if this is JSON, try to parse it.
            if buf:
                f.write(buf)
                buf = json.loads(buf)
                
                
                '''
                PC has to know the order of adc1, adc2 later. (write it in a file)
                expected buf :
                1. action JSON:
                {
                    'command': 'action',
                    'action1': adc1,
                    'action2': adc2}
                2. termination JSON:
                {
                    'command': 'end'}
                '''
                
                if buf['command'] == 'action':
                    action = {} # expects it to be a dict
                    try:
                        action[sl[0]] = buf['action1']
                        action[sl[1]] = buf['action2']
                    except:
                        raise ValueError # does not have the data
                        
                    f.write(json.dumps(action))
                    f.close()
                    runner_obj.mb.set_led_color('none')
                    return
                        
                    # broadcast to the slaves (step 2)
                    runner_obj.mb.e.send(None, json.dumps({'tag':'rl_action',
                                                     'action': action,
                                                     'is_queen':runner_obj.mb.is_queen}))
                        
                    # block until all the slaves send their feedbacks (step 3)
                    while list(runner_obj.recv_flags.values()) != [True, True]:
                        pass
                        
                        
                        
                    # send the saved states to the PC via serial (step 4)
                    # expected states form : dict
                    serial_msg = json.dumps({'tag' : 'next_state', 'next_state' : runner_obj.recv_states})
                    print(serial_msg)
                    
                if buf['command'] == 'end':
                    # send the slaves 'END' messages
                    runner_obj.mb.e.send(None, json.dumps({'tag':'rl_end',
                                                     'is_queen':runner_obj.mb.is_queen}))
                    # send the serial an 'END' message
                    serial_msg = json.dumps({'tag' : 'end_serial'})
                    print(serial_msg)
                        
                    # end the queen's RL pipeline
                    return 0 # ended well
                
                
        else: # slave, as agents
            '''
            1. receive action from the queen (controller)
            2. perform that action
            3. emit the result (10D)
            4. wait until the next action comes 
            '''    
            motor_value = -1
            # block until message arrives from the queen (rl_action) - step 1 & 4
            while True:
                if runner_obj.mb.received_msg:
                    try:
                        json_msg = json.loads(runner_obj.mb.received_msg)
                    except:
                        raise ValueError
                    if json_msg['tag'] == 'rl_action':
                        motor_val = json_msg['action'][runner_obj.mb.mac_addr]
                        runner_obj.mb.received_msg = None
                        runner_obj.mb.received_mac = None # clear buffer
                        break
                    if json_msg['tag'] == 'rl_end':
                        runner_obj.mb.received_msg = None
                        runner_obj.mb.received_mac = None
                        return 0 # ended well
                    # if feedback msg arrived, just keep on blocking
                
            # perform action (play for 50 ms) - step 2
            for _ in range(50):
                runner_obj.mb.sync_move_motor(motor_val)
                
            ax, ay, az = lsm.read_accel()
            mx, my, mz = lsm.read_magnet()
            gx, gy, gz = lsm.read_gyro()
            adc = runner_obj.mb.adc.read()
            # add distance value to this part later !!
                
            feedback = [ax, ay, az, mx, my, mz, gx, gy, gz, adc] # 10-D list
                
            runner_obj.mb.e.send(None, json.dumps({'tag':'rl_feedback',
                                             'next_state': feedback,
                                             'is_queen':runner_obj.mb.is_queen}))
from utime import sleep_ms    
import binascii
import json
    
def grouping(runner_obj):    
    # correct grouping based on callback
    if runner_obj.mb.is_queen:
                        
                        
        sleep_ms(1500) # wait 1.5s (listen)
        # if queen received None, one-to-all
        # if queen received something, grouping
        # think of other cases
                        
            
        if runner_obj.mb.received_msg is None:
            # if net table is not empty, multicast to peers
                            
            hex_net_table = [binascii.hexlify(m).decode() for m in runner_obj.mb.net_table]
            if len(runner_obj.mb.net_table) > 1:
                runner_obj.mb.e.send(None, json.dumps({'tag':'distribute',
                                                       'is_queen':True,
                                                       'net_table':hex_net_table}))
                                
                            
                            
        else: # grouping / ungrouping
            msg_obj = json.loads(runner_obj.mb.received_msg)
            hex_mac = binascii.hexlify(runner_obj.mb.received_mac).decode()
                            
            if runner_obj.mb.received_mac in runner_obj.mb.net_table: # ungrouping
                runner_obj.mb.net_table.remove(runner_obj.mb.received_mac)
                runner_obj.mb.e.send(runner_obj.mb.received_mac, json.dumps({'tag':'ungrouping',
                                                                             'is_queen':True}))
                runner_obj.mb.e.del_peer(runner_obj.mb.received_mac)
                            
            else: # grouping
                runner_obj.mb.net_table.append(runner_obj.mb.received_mac)
                runner_obj.mb.e.add_peer(runner_obj.mb.received_mac)
                runner_obj.mb.e.send(runner_obj.mb.received_mac, json.dumps({'tag':'grouping',
                                                                             'is_queen':True}))
                                               
                        
        # clear the flag to receive new message
        runner_obj.mb.received_msg = None
        runner_obj.mb.received_mac = None
                        
                        
                        
                        
    else: # slave (no conflict with 'distribute', this waits 1s only if longbttn pressed.)
        # send grouping message
        runner_obj.mb.e.send(b'\xff'*6, json.dumps({'tag':'grouping', 'is_queen':runner_obj.mb.is_queen}))
        # if queen mac addr is in net table, ungroup/ else group
        sleep_ms(3500) # wait 3.5s (expect button async)
                        
        # if no received message, queen was not pressed at the same time (approx.).
        if runner_obj.mb.received_msg is None:
            pass # do nothing
                        
        else:
            # assume we received the msg
            msg_obj = json.loads(runner_obj.mb.received_msg)
                            
            # ignore slaves' messages
            if not msg_obj['is_queen']:
                runner_obj.mb.received_msg = None
                runner_obj.mb.received_mac = None # clear the buffer
                return -1 # skip to the next main routine loop
            queen_mac = runner_obj.mb.received_mac
                            
            if msg_obj['tag'] == 'grouping': # group with the queen
                if queen_mac not in runner_obj.mb.net_table:
                    runner_obj.mb.net_table.append(queen_mac)
                    runner_obj.mb.e.add_peer(queen_mac)
            elif msg_obj['tag'] == 'ungrouping': # ungroup with the queen
                if queen_mac in runner_obj.mb.net_table:
                    runner_obj.mb.net_table.remove(queen_mac)
                    runner_obj.mb.e.del_peer(queen_mac)
                            
                        
        # clear the flag to receive new message
        runner_obj.mb.received_msg = None
        runner_obj.mb.received_mac = None
        
    print(f'net table : {runner_obj.mb.net_table}')
    return 0 # done well
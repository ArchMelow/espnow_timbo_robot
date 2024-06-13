import espnow

'''
library to create and load network table
(NOT USED)
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
    
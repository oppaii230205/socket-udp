from fileinput import filename
import os
from socket import socket, AF_INET, SOCK_DGRAM
from socket import timeout
import struct
import threading
import hashlib
import sys

SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
BUFFER_SIZE = 1024
TIMEOUT = 5  # Timeout for waiting for ACK
NUM_PARTS = 4
HEADER_FORMAT = '>H B'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
SERVER_ID = 1

def calculate_checksum(data):
    # Tạo MD5 hash của dữ liệu
    hash_bytes = hashlib.md5(data).digest()  # MD5 trả về 16 bytes
    # Lấy 2 byte đầu tiên của MD5 và chuyển thành số nguyên 16-bit
    short_checksum = int.from_bytes(hash_bytes[:2], byteorder='big')
    # Đảm bảo giá trị nằm trong phạm vi 16-bit
    return ~short_checksum & 0xFFFF

def unpack(packet):
    packet_header = packet[:HEADER_SIZE]
    data = packet[HEADER_SIZE:]
    checksum, seq_num = struct.unpack(HEADER_FORMAT,packet_header)
    return checksum, seq_num, data

def send_msg(sock, addr, data, sequence_number):
    check_sum = calculate_checksum(sequence_number[0].to_bytes(1, byteorder='big') + data)
    packet = struct.pack(HEADER_FORMAT, check_sum, sequence_number[0]) + data
    while True:
        sock.sendto(packet, addr)
        try:
            sock.settimeout(TIMEOUT)
            ack, _ = sock.recvfrom(BUFFER_SIZE)
            # ack_checkSum = int.from_bytes(ack[:2], byteorder='big')
            # seq_num = ack[2]
            ack_checkSum, seq_num, _ = unpack(ack);
            if seq_num == sequence_number[0] and ack_checkSum == calculate_checksum(seq_num.to_bytes(1, byteorder='big')):
                sequence_number[0] = 1 - sequence_number[0]
                break
        except timeout:
            continue



def recv_msg(sock, sequence_number):
    while True:
        try:
            packet, sender_addr = sock.recvfrom(BUFFER_SIZE)
            received_checksum, seq_num, data = unpack(packet)
            if received_checksum == calculate_checksum(seq_num.to_bytes(1, byteorder='big') + data):
                ack_checksum = calculate_checksum(seq_num.to_bytes(1, byteorder='big'))
                ack_packet = ack_checksum.to_bytes(2, byteorder='big') + seq_num.to_bytes(1, byteorder='big')
                sock.sendto(ack_packet, sender_addr)
                if seq_num != sequence_number[1]:
                    sequence_number[1] = seq_num
                    return data, sender_addr
            else:
                continue
        except timeout:
            continue

def send_part(server_socket, addr, file_name, file_size, part_size, part_index, sequence_number): 
     # Open file and send it in chunks
     with open(file_name, mode='rb') as f:
        f.seek(part_index * part_size) # Always seek to the right position, check part_size later        

        #print(f">> file_name: {file_name}, part_index: {part_index} is going to be sent!")


        if part_index == NUM_PARTS - 1:
            part_size = file_size - part_index * part_size

        data = bytearray()
        while len(data) < part_size:
            # Read a chunk of the file (BUFFER_SIZE - 3 for headers)
            chunk = f.read(min(part_size - len(data), BUFFER_SIZE - 3))
            # print(chunk)
            # If chunk is empty (end of file), break
            if not chunk:
                break
                    
            # Send the current chunk
            send_msg(server_socket, addr, chunk, sequence_number)
            data.extend(chunk)

            # Display progress
            # print(f"Sent {len(data)}/{part_size} bytes.")
        
        #print(f">> file_name: {file_name}, part_index: {part_index} has been sent!")
        

def handle_client(server_socket, client_addr, msg):
    # server_socket = socket(AF_INET, SOCK_DGRAM)
    # server_socket.bind((SERVER_HOST, SERVER_PORT))
    # print(f"Server is listening on {SERVER_HOST}:{SERVER_PORT}")
    # sequence_number = [0, 1]  # Initialize sequence number to 0

    try:
        # Receive the requested file name from the client
        sequence_number = [0, 1]  # Initialize sequence number to 0

        # msg, client_addr = recv_msg(server_socket, sequence_number)
        argument_list = msg.decode('utf-8').split(',')

        # file_name and part_index received
        if len(argument_list) == 2:
            file_name = argument_list[0]
            part_index = int(argument_list[1])

            # Check if file exists and send the file size
            if os.path.exists(file_name):
                file_size = os.path.getsize(file_name)
                part_size = file_size // NUM_PARTS
                # msg = f"{file_size}, {part_size}".encode('utf-8')
                # send_msg(server_socket, client_addr, msg, sequence_number)
                # print(f"file_name: {file_name}, part_index: {part_index}")
                
                send_part(server_socket, client_addr, file_name, file_size, part_size, part_index, sequence_number)
                                    
                # print(f"File {file_name} sent to {client_addr} successfully.")
            else:
                print(f"File {file_name} not found.")
                send_msg(server_socket, client_addr, b"File not found", sequence_number)

        # Just file_name received
        elif len(argument_list) == 1:
            file_name = argument_list[0]

            if file_name == "start":
                file_size = os.path.getsize("input.txt")
                send_msg(server_socket, client_addr,str(file_size).encode('utf8'), sequence_number)
                with open("input.txt", 'rb') as file:
                    data = b''
                    while len(data) < file_size:
                        chunk = file.read(BUFFER_SIZE-3)
                        data += chunk
                        send_msg(server_socket, client_addr, chunk, sequence_number)
                    
            # Check if file exists and send the file size
            else:
                if os.path.exists(file_name):
                    file_size = os.path.getsize(file_name)
                    part_size = file_size // NUM_PARTS
                    msg = f"{file_size},{part_size}".encode('utf-8')
                    send_msg(server_socket, client_addr, msg, sequence_number)
                    print(f"{file_name} is going to be sent!")
                    # print(f"Sending file size {file_size} bytes, part size {part_size} bytes")

                    # print(f"File {file_name} sent to {client_addr} successfully.")
                else:
                    print(f"File {file_name} not found.")
                    send_msg(server_socket, client_addr, b"File not found,0", sequence_number)

    except Exception as e:
        print(f"Server error: {e}")
        


def start_server():
    global SERVER_ID
    server_socket = socket(AF_INET, SOCK_DGRAM)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    print(f"Server is listening on {SERVER_HOST}:{SERVER_PORT}")

    while True:
        sequence_number = [0, 1]  # Initialize sequence number to 0
        msg, client_addr = recv_msg(server_socket, sequence_number)
        sub_server_socket = socket(AF_INET, SOCK_DGRAM)
        sub_server_socket.bind((SERVER_HOST, SERVER_PORT + SERVER_ID))
        SERVER_ID += 1
        client_handler = threading.Thread(target=handle_client, args=(sub_server_socket, client_addr, msg))
        client_handler.start()

if __name__ == "__main__":
    start_server()

import os
from socket import socket, AF_INET, SOCK_DGRAM
from socket import timeout
import struct
import threading
import signal

SERVER_HOST = 'localhost'
SERVER_PORT = 5000
BUFFER_SIZE = 1024
NUMS_PART = 4
TIMEOUT = 1  # Timeout for waiting for ACK
HEADER_FORMAT = '>H B'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

def calculate_checksum(data):
    checksum = 0
    # Divide data into 16-bit words
    for i in range(0, len(data), 2):
        if i + 1 < len(data):
            word = (data[i] << 8) + data[i + 1]  # Combine 2 bytes into a 16-bit word
        else:
            word = data[i] << 8  # Last byte, padded with a 0
        checksum += word
        # Handle overflow by wrapping around
        checksum = (checksum & 0xFFFF) + (checksum >> 16)

    # Take the one's complement
    return ~checksum & 0xFFFF


def send_msg(sock, addr, data, sequence_number):
    check_sum = calculate_checksum(sequence_number[0].to_bytes(1, byteorder='big') + data)
    #packet = check_sum.to_bytes(2, byteorder='big') + sequence_number[0].to_bytes(1, byteorder='big') + data
    packet = struct.pack(HEADER_FORMAT, check_sum, sequence_number[0]) + data
    while True:
        sock.sendto(packet, addr)
        try:
            sock.settimeout(TIMEOUT)
            ack, _ = sock.recvfrom(BUFFER_SIZE)
            ack_checkSum = int.from_bytes(ack[:2], byteorder='big')
            seq_num = ack[2]
            if seq_num == sequence_number[0] and ack_checkSum == calculate_checksum(seq_num.to_bytes(1, byteorder='big')):
                sequence_number[0] = 1 - sequence_number[0]
                break
        except timeout:
            continue


def unpack(packet):
    packet_header = packet[:HEADER_SIZE]
    data = packet[HEADER_SIZE:]
    checksum, seq_num = struct.unpack(HEADER_FORMAT,packet_header)
    return checksum, seq_num, data

def recv_msg(sock, sequence_number):
    while True:
        try:
            packet, sender_addr = sock.recvfrom(BUFFER_SIZE)
            received_checksum, seq_num, data = unpack(packet)
            if received_checksum == calculate_checksum(seq_num.to_bytes(1, byteorder='big') + data):
                ack_checksum = calculate_checksum(seq_num.to_bytes(1, byteorder='big'))
                #ack_packet = ack_checksum.to_bytes(2, byteorder='big') + seq_num.to_bytes(1, byteorder='big')
                ack_packet = struct.pack(HEADER_FORMAT,ack_checksum, seq_num)
                sock.sendto(ack_packet, sender_addr)
                if seq_num != sequence_number[1]:
                    sequence_number[1] = seq_num
                    return data, sender_addr
        except timeout:
            continue

def recv_part(server_addr, file_name, file_size, part_size, part_index):
    child_client_socket = socket(AF_INET, SOCK_DGRAM) 
    
    sequence_number = [0, 1]  # Initialize sequence number to 0

    # Send "file_name,part_index" to server
    send_msg(child_client_socket, server_addr, f"{file_name},{part_index}".encode('utf-8'), sequence_number)

    # Open the file for writing and ensure it is empty
    client_filename = file_name.split('.')
    with open(client_filename[0]+"_client."+client_filename[1], 'r+b') as f:
        f.seek(part_index * part_size) # Always seek to the right position, check part_size later
        
        print(f">> file_name: {file_name}, part_index: {part_index} is going to be received!")

        if part_index == NUMS_PART - 1:
            part_size = file_size - part_index * part_size

        received = 0
        while received < part_size:
            # Receive the next chunk of the file
            chunk, _ = recv_msg(child_client_socket, sequence_number)
            # print(f"part_index: {part_index}: {chunk}")
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)

            # Calculate the percentage of the file received
            percent = (received / part_size) * 100
            # print(f"Received {received}/{part_size} bytes ({percent:.2f}%)")
        
        print(f">> file_name: {file_name}, part_index: {part_index} has been received!")
        
    child_client_socket.close()


def start_client():
    client_socket = socket(AF_INET, SOCK_DGRAM)
    server_addr = (SERVER_HOST, SERVER_PORT)

    sequence_number = [0, 1]

    # Request the file name from the server
    file_name = "server_1.txt"  # Replace with the file name you want to download
    send_msg(client_socket, server_addr, file_name.encode('utf-8'), sequence_number)
    
    # Receive file size and part_size information from the server
    msg, _ = recv_msg(client_socket, sequence_number)
    # print('Da nhan file size and part size')
    file_size, part_size = map(int, msg.decode('utf-8').split(','))
    # print(f"File size: {file_size} bytes, part size: {part_size} bytes")
    
    client_socket.close()
    
    client_filename = file_name.split('.')
    with open(client_filename[0]+"_client."+client_filename[1], 'wb') as f:
        f.truncate(file_size)

    threads = []
    for part_index in range(NUMS_PART):
        thread = threading.Thread(target=recv_part, args=(server_addr, file_name, file_size, part_size, part_index))
        thread.start()
        threads.append(thread)
        
    for thread in threads:
        thread.join()  # Wait for all threads to complete


    print(f"File {file_name} downloaded successfully.")


if __name__ == "__main__":
    start_client()
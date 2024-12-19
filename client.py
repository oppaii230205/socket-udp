import os
from socket import socket, AF_INET, SOCK_DGRAM
from socket import timeout
import struct
import threading
import signal
import hashlib
import sys
from colorama import init, Cursor

SERVER_HOST = '192.168.247.129'
SERVER_PORT = 5000
BUFFER_SIZE = 1024
NUM_PARTS = 4
TIMEOUT = 5  # Timeout for waiting for ACK
HEADER_FORMAT = '>H B'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FILE_ID = 0
NUM_OF_LINE = 0
init()

def gotoxy(x,y):
    sys.stdout.write(Cursor.POS(x, y))

def calculate_checksum(data):
    """Calculate a 16-bit checksum using hashlib (MD5)."""
    # Tạo MD5 hash của dữ liệu
    hash_bytes = hashlib.md5(data).digest()  # MD5 trả về 16 bytes
    # Lấy 2 byte đầu tiên của MD5 và chuyển thành số nguyên 16-bit
    short_checksum = int.from_bytes(hash_bytes[:2], byteorder='big')
    # Đảm bảo giá trị nằm trong phạm vi 16-bit
    return ~short_checksum & 0xFFFF
 

def send_msg(sock, addr, data, sequence_number):
    check_sum = calculate_checksum(sequence_number[0].to_bytes(1, byteorder='big') + data)
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
                ack_packet = struct.pack(HEADER_FORMAT,ack_checksum, seq_num)
                sock.sendto(ack_packet, sender_addr)
                if seq_num != sequence_number[1]:
                    sequence_number[1] = seq_num
                    return data, sender_addr
        except timeout:
            continue

def recv_part(server_addr, file_name, file_size, part_size, part_index):
    child_client_socket = socket(AF_INET, SOCK_DGRAM) 
    global FILE_ID, NUM_OF_LINE
    sequence_number = [0, 1]  # Initialize sequence number to 0

    # Send "file_name,part_index" to server
    send_msg(child_client_socket, server_addr, f"{file_name},{part_index}".encode('utf-8'), sequence_number)

    # Open the file for writing and ensure it is empty
    with open(file_name, 'r+b') as f:
        f.seek(part_index * part_size) # Always seek to the right position, check part_size later
        
        if part_index == NUM_PARTS - 1:
            part_size = file_size - part_index * part_size

        received = 0
        while received < part_size:
            # Receive the next chunk of the file
            chunk, _ = recv_msg(child_client_socket, sequence_number)
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)

            # Calculate the percentage of the file received
            percent = (received / part_size) * 100
            
            gotoxy(1,NUM_OF_LINE + (part_index + 1 + 10 * FILE_ID + 1))
            print(f"Part {part_index} Received {received}/{part_size} bytes ({percent:.2f}%)")
        
    child_client_socket.close()


def print_server_text(data):
    os.system('cls')
    print(">> ----------  DOWLOAD LIST  -------- <<")
    print(data)
    print(">> ---------------------------------- <<")
def start_client():
    client_socket = socket(AF_INET, SOCK_DGRAM)
    server_addr = (SERVER_HOST, SERVER_PORT)
    try:
        global FILE_ID, NUM_OF_LINE
        sequence_number = [0, 1]

        # Request the file name from the server
        file_name = "start"  # Replace with the file name you want to download
        send_msg(client_socket, server_addr, file_name.encode('utf-8'), sequence_number)
    
        msg, _ =recv_msg(client_socket, sequence_number)
        file_size = int(msg.decode('utf8'))
        data=b''
        with open("Data_Server.txt", 'wb') as file:
            while len(data) < file_size:
                chunk, _ = recv_msg(client_socket, sequence_number)
                file.write(chunk)
                data += chunk
        data = data.decode('utf8')
        with open("Data_Server.txt", 'rb') as file:
            while True:
                file_name = file.readline()
                if not file_name:
                    break
                NUM_OF_LINE += 1
        NUM_OF_LINE += 3
        print_server_text(data)
        # Receive file size and part_size information from the server
        with open('input.txt', 'r', encoding='utf8') as file:
            while True:
                try:
                    file_name = file.readline()
                    if not file_name:
                        break
                
                    file_name = file_name.strip()
                    sequence_number = [0, 1]
                    send_msg(client_socket, server_addr, file_name.encode('utf-8'), sequence_number)
                    msg, _ = recv_msg(client_socket, sequence_number)
                    file_size, part_size = map(int, msg.decode('utf-8').split(','))

                    gotoxy(1,NUM_OF_LINE + (10 * FILE_ID + 1))
                    print(f"{file_name} is going to be dowloaded")

                    with open(file_name, 'wb') as f:
                        f.truncate(file_size)

                    threads = []
                    for part_index in range(NUM_PARTS):
                        thread = threading.Thread(target=recv_part, args=(server_addr, file_name, file_size, part_size, part_index))
                        thread.start()
                        threads.append(thread)
        
                    for thread in threads:
                        thread.join()  # Wait for all threads to complete
                    gotoxy(1,NUM_OF_LINE + (5 + 10 * FILE_ID + 1))
                    print(f"File {file_name} downloaded successfully.\n")
                    FILE_ID += 1
                    if FILE_ID >= 2:
                        FILE_ID = 0
                        print_server_text(data)                 

                except:
                    print(file_name,"not found")
                    continue
    except:
        print("Error")
        client_socket.close()

if __name__ == "__main__":
    start_client()

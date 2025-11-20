#!/usr/bin/env python3
import select
import sys
import socket
import threading
from handlers.client_handler import handle_client
import cache
import http_utils

# $ python3 proxy.py <port> <timeout> <max_object_size> <max_cache_size>
port = int(sys.argv[1])
timeout = int(sys.argv[2])
max_object_size = int(sys.argv[3])
max_cache_size = int(sys.argv[4])

# initialize cache and timeout
cache.init_cache(max_object_size, max_cache_size)
http_utils.set_timeout(timeout)

host = "0.0.0.0"

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # 1. connect client-proxy
    s.bind((host, port))
    s.listen()
    while True:
        conn, addr = s.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr, port, timeout), daemon=True)
        thread.start()

import socket
from urllib.parse import urlparse

timeout = 5

def set_timeout(t):
    global timeout
    timeout = t

# returns normalised form of a url
def normaliseURL(parser):
    norm_scheme = parser.scheme.lower()
    norm_host = parser.hostname.lower()
    norm_port = parser.port
    if norm_port == 80 or norm_port is None:
        port_str = ""
    else:
        port_str = f":{norm_port}"
    norm_path = parser.path if parser.path != "" else "/"
    norm_query = f"?{parser.query}" if parser.query else ""

    return f"{norm_scheme}://{norm_host}{port_str}{norm_path}{norm_query}"

# handles receiving data from origin server
def httpResponse(server_sock, method):
    # 5.2 receive all the data transmitted by server
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = server_sock.recv(1024)
        if not chunk:
            break
        data += chunk

    if not data:
        raise Exception("No server response")

    header, body = data.split(b"\r\n\r\n", 1)

    # 5.3 parse start_line
    start_line = header.decode().split("\r\n")[0]
    http_version, status_code, reason = start_line.split(" ", 2)

    # 5.4 read header lines into dict
    header_lines = header.decode().split("\r\n")[1:]
    headers = {}
    for line in header_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    content_length = headers.get("content-length")
    transfer_encoding = headers.get("transfer-encoding")

    # there is no body present
    if method == "HEAD" or status_code in {"204", "304"}:
        pass

    # existing content length
    elif content_length is not None and transfer_encoding is None:
        content_length = int(content_length)
        remaining = content_length - len(body)

        # read all of body
        while remaining > 0:
            chunk = server_sock.recv(min(1024, remaining))
            if not chunk:
                break
            body += chunk
            remaining -= len(chunk)
    
    # no fields or has transfer encoding
    else:
        while True:
            chunk = server_sock.recv(1024)
            if not chunk:
                break
            body += chunk

    response_line = f"{http_version} {status_code} {reason}\r\n"
    return response_line, headers, body
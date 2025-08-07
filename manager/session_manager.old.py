import socket
import subprocess
import uuid

server_registry = {}  # client_id → {"port": ..., "process": ..., "socket": ...}


def find_free_port(start=5555, end=6000):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports available")


def launch_phoebe_server():
    client_id = str(uuid.uuid4())
    port = find_free_port()
    proc = subprocess.Popen(["python", "app/phoebe_server.py", str(port)])
    server_registry[client_id] = {"port": port, "process": proc}
    return client_id, port


def get_server_info(client_id):
    return server_registry.get(client_id)


def shutdown_server(client_id):
    info = server_registry.get(client_id)
    if info:
        info["process"].terminate()
        info["process"].wait()
        del server_registry[client_id]
        return True
    return False

import tomllib
import uuid
import logging
import time
import psutil
from typing import Dict, Optional, Set

logger = logging.getLogger("uvicorn")

# Registry mapping client_id -> server metadata
server_registry: Dict[str, Dict[str, object]] = {}
reserved_ports: Set[int] = set()
PORT_POOL: Set[int] = set()


def load_port_config(path: str = "manager/config.toml"):
    global PORT_POOL
    with open(path, "rb") as f:
        config = tomllib.load(f)
    start = config['port_pool']['start']
    end = config['port_pool']['end']
    PORT_POOL = set(range(start, end))
    logger.info(f'{PORT_POOL=}')


def request_port() -> int:
    for port in PORT_POOL:
        if port not in reserved_ports:
            reserved_ports.add(port)
            return port
    raise RuntimeError("No available ports in pool")


def launch_phoebe_server() -> Dict[str, object]:
    """
    Launch a dedicated phoebe_server instance for a new client.
    Returns a dict with client_id and port.
    """
    client_id = str(uuid.uuid4())
    port = request_port()
    timestamp = time.ctime()

    proc = psutil.Popen([
        "python", "server/server.py", str(port)
    ])

    # Placeholder for memory usage, will be updated later
    mem_used = 0.0

    server_registry[client_id] = {
        'client_id': client_id,
        'process': proc,
        'timestamp': timestamp,
        'mem_used': mem_used,
        'port': port
    }

    # Need to pop 'process' because it cannot be serialized over http
    return {k: v for k, v in server_registry[client_id].items() if k != 'process'}


def get_current_memory_usage(client_id: str) -> Optional[float]:
    """
    Get current memory usage of a running server process.
    """

    info = server_registry.get(client_id)
    if info and info.get('process'):
        proc = info['process']
        try:
            mem_used = proc.memory_info().rss / (2**20)  # MB
            server_registry[client_id]['mem_used'] = mem_used  # Update memory usage in registry
            return mem_used
        except psutil.NoSuchProcess:
            return None
    return None


def get_server_info(client_id: str) -> Optional[Dict[str, object]]:
    info = server_registry.get(client_id)
    return {k: v for k, v in info.items() if k != 'process'}


def shutdown_server(client_id: str) -> bool:
    info = server_registry.get(client_id)
    if info:
        proc = info.get("process")
        if proc:
            proc.terminate()
            proc.wait()
        del server_registry[client_id]
        return True
    return False


def list_sessions() -> Dict[str, Dict[str, object]]:
    """
    Return a list of all active client_ids and their metadata.
    """

    return {server: get_server_info(server) for server in server_registry.keys()}


# Load port configuration on module import
load_port_config()

import tomllib
import subprocess
import uuid
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger("uvicorn")

# Registry mapping client_id -> server metadata
server_registry: Dict[str, Dict[str, object]] = {}
reserved_ports: Set[int] = set()
PORT_POOL: Set[int] = set()


def load_port_config(path: str = "config.toml"):
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

    proc = subprocess.Popen([
        "python", "server/server.py", str(port)
    ])

    server_registry[client_id] = {
        "port": port,
        "process": proc
    }

    return {"client_id": client_id, "port": port}


def get_server_info(client_id: str) -> Optional[Dict[str, object]]:
    return server_registry.get(client_id)


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


def list_sessions() -> Dict[str, int]:
    """Return a list of all active client_ids and their ports."""
    return {cid: meta["port"] for cid, meta in server_registry.items() if "port" in meta}


# Load port configuration on module import
load_port_config()

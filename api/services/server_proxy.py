import zmq

def send_command(port: int, command: dict) -> dict:
    ctx = zmq.Context()
    s = ctx.socket(zmq.REQ)
    s.connect(f"tcp://localhost:{port}")
    s.send_json(command)
    reply = s.recv_json()
    return reply

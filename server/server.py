import sys
import zmq
import phoebe

def main(port: int):
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REP)
    socket.bind(f"tcp://0.0.0.0:{port}")
    print(f"[phoebe_server] Running on port {port}")

    b = phoebe.default_binary()
    b.flip_constraint('mass@primary', solve_for='q@binary')
    b.flip_constraint('mass@secondary', solve_for='sma@binary')

    while True:
        message = socket.recv_json()
        print(f"[phoebe_server] Received: {message}")

        # handle message
        if message.get("cmd") == "status":
            socket.send_json({"status": "ok", "port": port})
        else:
            socket.send_json({"error": "Unknown command"})

if __name__ == "__main__":
    port = int(sys.argv[1])
    main(port)

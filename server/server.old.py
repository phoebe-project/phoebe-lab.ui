import phoebe
import zmq
import sys


def main(port):
    b = phoebe.default_binary()
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")
    print(f"[PHOEBE SERVER] Listening on tcp://*:{port}")
    sys.stdout.flush()

    while True:
        msg = socket.recv_json()
        cmd = msg.get("command")

        if cmd == "set":
            b[msg["param"]] = msg["value"]
            socket.send_json({"status": "ok"})

        elif cmd == "get":
            val = b[msg["param"]].get_value()
            socket.send_json({"value": val})

        elif cmd == "compute":
            b.add_dataset('lc', compute_times=phoebe.linspace(0, 1, 101), passband='Johnson:V')
            b.run_compute()
            fluxes = b['value@fluxes@model'].tolist()
            socket.send_json({"status": "ok", "fluxes": fluxes})

        else:
            socket.send_json({"error": "unknown command"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5555
    main(port)

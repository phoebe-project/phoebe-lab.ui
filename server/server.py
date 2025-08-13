import sys
import zmq
import phoebe
import traceback


class PhoebeServer:
    """Phoebe ZMQ server that handles bundle operations."""

    def __init__(self, port: int):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://0.0.0.0:{port}")

        # Create a Phoebe bundle and set up the environment
        self.bundle = phoebe.default_binary()
        self.bundle.flip_constraint('mass@primary', solve_for='q@binary')
        self.bundle.flip_constraint('mass@secondary', solve_for='sma@binary')

        # Command registry
        self.commands = {
            'phoebe.version': self.version,
            # 'to_phase': self.to_phase,
            # 'add_dataset': self.add_dataset,
            # 'info': self.bundle_info,
            'status': self.status
        }

        print(f"[phoebe_server] Running on port {port}")

    def run_command(self, message):
        """Process a single command message."""
        cmd_name = message.get("cmd")

        if cmd_name in self.commands:
            try:
                # Get command parameters (exclude 'cmd' field)
                params = {k: v for k, v in message.items() if k != 'cmd'}

                # Execute the registered command
                result = self.commands[cmd_name](**params)

                # Send back the result
                response = {
                    "status": "success",
                    "result": result
                }

                # Handle special cases for specific command types
                # if cmd_name == "to_phase":
                #     # If it's a phase calculation, ensure result is serializable
                #     if hasattr(result, 'tolist'):
                #         response["phases"] = result.tolist()
                #     else:
                #         response["phases"] = list(result) if hasattr(result, '__iter__') else [result]

                print(f"[phoebe_server] Command '{cmd_name}' executed successfully")
                return response

            except Exception as e:
                error_response = {
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
                print(f"[phoebe_server] Error executing command '{cmd_name}': {e}")
                return error_response
        else:
            return {
                "status": "error",
                "error": f"Unknown command: {cmd_name}",
                "available_commands": list(self.commands.keys())
            }

    def version(self):
        """Get Phoebe version."""
        return phoebe.__version__

    # def to_phase(self, times, t0_supconj=0.0, period=1.0):
    #     """Calculate phases from times."""
    #     return self.bundle.to_phase(times, t0_supconj=t0_supconj, period=period)

    # def add_dataset(self, kind='lc', times=None, fluxes=None, sigmas=None, **kwargs):
    #     """Add dataset to bundle."""
    #     times = times or []
    #     fluxes = fluxes or []
    #     sigmas = sigmas or []

    #     # For now, just return success (in real implementation, add to bundle)
    #     # self.bundle.add_dataset(kind, times=times, fluxes=fluxes, sigmas=sigmas, **kwargs)
    #     return {"dataset_added": True, "num_points": len(times)}

    # def bundle_info(self):
    #     """Get bundle information."""
    #     return {"num_parameters": len(self.bundle.get_parameters())}

    def status(self):
        """Get server status."""
        return {"status": "ok", "port": self.port}

    def run(self):
        """Main server loop."""
        while True:
            try:
                message = self.socket.recv_json()
                print(f"[phoebe_server] Received: {message}")

                response = self.run_command(message)
                self.socket.send_json(response)

            except KeyboardInterrupt:
                print("\n[phoebe_server] Shutting down...")
                break
            except Exception as e:
                print(f"[phoebe_server] Unexpected error: {e}")
                error_response = {
                    "status": "error",
                    "error": f"Server error: {str(e)}",
                    "traceback": traceback.format_exc()
                }
                self.socket.send_json(error_response)

    def cleanup(self):
        """Clean up resources."""
        self.socket.close()
        self.context.term()


def main(port: int):
    """Main entry point."""
    server = PhoebeServer(port)
    try:
        server.run()
    finally:
        server.cleanup()


if __name__ == "__main__":
    port = int(sys.argv[1])
    main(port)

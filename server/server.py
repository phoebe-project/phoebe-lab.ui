import sys
import zmq
import phoebe
import traceback
from common.serialization import make_json_serializable


class PhoebeServer:
    """Phoebe ZMQ server that handles bundle operations."""

    def __init__(self, port: int):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://0.0.0.0:{port}")

        # Create a Phoebe bundle, parametrize for the UI and
        # initialize a dc solver:
        self.bundle = phoebe.default_binary()
        self.bundle.flip_constraint('mass@primary', solve_for='q@binary')
        self.bundle.flip_constraint('mass@secondary', solve_for='sma@binary')
        self.bundle.add_solver('differential_corrections', solver='dc')

        # Command registry
        self.commands = {
            'phoebe.version': self.version,
            'b.set_value': self.set_value,
            'b.add_dataset': self.add_dataset,
            'b.remove_dataset': self.remove_dataset,
            'b.run_compute': self.run_compute,
            'b.run_solver': self.run_solver,
            'status': self.status
        }

        print(f"[phoebe_server] Running on port {port}")

    def run_command(self, message):
        """Process a single command message."""
        cmd_name = message.get('cmd')

        if cmd_name in self.commands:
            try:
                # Get command parameters from 'params' key
                params = message.get('params', {})

                # Execute the registered command
                result = self.commands[cmd_name](**params)

                # Make result JSON-serializable
                serializable_result = make_json_serializable(result)

                # Send back the result
                response = {
                    "status": "success",
                    "result": serializable_result
                }

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

    def set_value(self, **kwargs):
        """Set a parameter value in the Phoebe bundle."""
        # Extract required parameters
        twig = kwargs.pop('twig', None)
        value = kwargs.pop('value', None)

        # Validate required parameters
        if twig is None:
            raise ValueError("twig parameter is required for set_value")
        if value is None:
            raise ValueError("value parameter is required for set_value")

        # Call Phoebe's set_value method
        self.bundle.set_value(twig, value)
        return {"status": f"Parameter {twig} set to {value} successfully"}

    def add_dataset(self, **kwargs):
        """Add a dataset to the Phoebe bundle."""
        # Extract kind as required positional argument
        if 'kind' not in kwargs:
            raise ValueError("kind parameter is required for add_dataset")

        kind = kwargs.pop('kind')

        # Call Phoebe's add_dataset with kind as positional arg and rest as kwargs
        self.bundle.add_dataset(kind, **kwargs)

        return {"status": "Dataset added successfully"}

    def remove_dataset(self, **kwargs):
        """Remove a dataset from the Phoebe bundle."""
        dataset = kwargs.pop('dataset', None)

        if dataset is None:
            raise ValueError("dataset parameter is required for remove_dataset")

        self.bundle.remove_dataset(dataset)
        return {"status": f"Dataset {dataset} removed successfully"}

    def run_compute(self, **kwargs):
        """Run the Phoebe compute model.

        Parameters:
        -----------
        **kwargs : dict
            Optional parameters for the compute (e.g., compute='preview', etc.)

        Returns:
        --------
        dict
            Dictionary containing model results (fluxes, rvs, etc.)
        """

        # Run the computation with any provided kwargs
        self.bundle.run_compute(**kwargs)

        # Return model results
        result = {}

        # We now need to traverse all datasets and assign the results accordingly:
        for dataset in self.bundle.datasets:
            kind = self.bundle[f'{dataset}@dataset'].kind  # 'lc' or 'rv'

            result[dataset] = {}
            result[dataset]['times'] = self.bundle.get_value('compute_times', dataset=dataset, context='dataset')
            result[dataset]['phases'] = self.bundle.get_value('compute_phases', dataset=dataset, context='dataset')

            if kind == 'lc':
                result[dataset]['fluxes'] = self.bundle.get_value('fluxes', dataset=dataset, context='model')
            if kind == 'rv':
                result[dataset]['rv1s'] = self.bundle.get_value('rvs', dataset=dataset, component='primary', context='model')
                result[dataset]['rv2s'] = self.bundle.get_value('rvs', dataset=dataset, component='secondary', context='model')

        return {"status": "Compute completed successfully", "model": result}

    def run_solver(self, **kwargs):
        # Run the solver:
        self.bundle.run_solver(**kwargs)

        fit_parameters = self.bundle.get_value('fit_parameters', context='solver')
        init_values = self.bundle.get_value('initial_values', context='solver')
        fitted_values = self.bundle.get_value('fitted_values', context='solution')

        result = {
            'fit_parameters': fit_parameters,
            'initial_values': init_values,
            'fitted_values': fitted_values,
        }

        return {
            'status': 'Solver completed successfully',
            'solution': result
        }

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

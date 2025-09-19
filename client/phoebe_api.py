"""Phoebe API client for communicating with Phoebe sessions."""

import requests
from common.serialization import make_json_serializable


class PhoebeAPI:
    """API client for Phoebe parameter operations."""

    def __init__(self, base_url: str = "http://localhost:8001", client_id: str = None):
        self.base_url = base_url
        self.client_id = client_id

    def set_client_id(self, client_id: str):
        """Set the client ID for this API instance."""
        self.client_id = client_id

    def send_command(self, command: dict):
        """Send a general command to the Phoebe session."""
        if not self.client_id:
            raise ValueError("No client ID set. Call set_client_id() first or provide client_id in constructor.")

        # Serialize the command to ensure JSON compatibility
        serializable_command = make_json_serializable(command)

        response = requests.post(f"{self.base_url}/send/{self.client_id}", json=serializable_command)
        response.raise_for_status()
        return response.json()

    def change_morphology(self, morphology):
        command = {
            'cmd': 'b.default_binary',
            'params': {'morphology': morphology}
        }
        return self.send_command(command)

    def get_parameter(self, twig: str):
        if not twig:
            raise ValueError('twig parameter cannot be empty.')

        command = {
            'cmd': 'b.get_parameter',
            'params': {'twig': twig}
        }
        return self.send_command(command)

    def is_parameter_constrained(self, twig: str = None, uniqueid: str = None):
        if not twig and not uniqueid:
            raise ValueError("either `twig` or `uniqueid` need to be passed")

        command = {
            'cmd': 'is_parameter_constrained',
            'params': {
                'twig': twig,
                'uniqueid': uniqueid
            }
        }
        return self.send_command(command)

    def get_value(self, twig: str = None, uniqueid: str = None):
        if twig is None and uniqueid is None:
            raise ValueError("either `twig` or `uniqueid` need to be passed")

        command = {
            'cmd': 'b.get_value',
            'params': {
                'twig': twig,
                'uniqueid': uniqueid
            }
        }
        return self.send_command(command)

    def get_uniqueid(self, twig: str = None):
        if twig is None:
            raise ValueError("`twig` parameter cannot be empty.")

        command = {
            'cmd': 'get_uniqueid',
            'params': {
                'twig': twig
            }
        }
        return self.send_command(command)

    def set_value(self, twig: str = None, uniqueid: str = None, value=None):
        if twig is None and uniqueid is None:
            raise ValueError("either `twig` or `uniqueid` need to be passed")
        if value is None:
            raise ValueError("`value` parameter missing")

        command = {
            'cmd': 'b.set_value',
            'params': {
                'twig': twig,
                'uniqueid': uniqueid,
                'value': value
            }
        }
        return self.send_command(command)

    def add_dataset(self, kind=None, **kwargs):
        """Add a dataset to the Phoebe session."""
        # If kind is passed as positional argument, add it to kwargs
        if kind is not None:
            kwargs['kind'] = kind

        command = {
            'cmd': 'b.add_dataset',
            'params': kwargs
        }

        return self.send_command(command)

    def remove_dataset(self, dataset: str):
        """Remove a dataset from the Phoebe session."""
        if not dataset:
            raise ValueError("dataset parameter cannot be empty")

        command = {
            'cmd': 'b.remove_dataset',
            'params': {
                'dataset': dataset
            }
        }
        return self.send_command(command)

    def run_compute(self, **kwargs):
        """Run the Phoebe computation with the current parameters.

        Parameters:
        -----------
        **kwargs : dict
            Optional parameters for the compute operation
            (e.g., compute='preview', model='phoebe', etc.)

        Returns:
        --------
        dict
            Response from the server with status and model results
        """
        command = {
            'cmd': 'b.run_compute',
            'params': kwargs
        }
        return self.send_command(command)

    def run_solver(self, **kwargs):
        command = {
            'cmd': 'b.run_solver',
            'params': kwargs
        }
        return self.send_command(command)

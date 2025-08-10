"""Phoebe API client for communicating with Phoebe sessions."""

import requests


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
        
        response = requests.post(f"{self.base_url}/send/{self.client_id}", json=command)
        response.raise_for_status()
        return response.json()

"""Session API client for communicating with the phoebe session management backend."""

import requests


class SessionAPI:
    """API client for session management operations."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url

    def get_sessions(self):
        """Get all active sessions."""
        response = requests.get(f"{self.base_url}/dash/sessions")
        response.raise_for_status()
        return response.json()

    def start_session(self):
        """Start a new session."""
        response = requests.post(f"{self.base_url}/dash/start-session")
        response.raise_for_status()
        return response.json()

    def end_session(self, client_id: str):
        """End a specific session."""
        response = requests.post(f"{self.base_url}/dash/end-session/{client_id}")
        response.raise_for_status()
        return response.json()

    def update_user_info(self, client_id: str, first_name: str, last_name: str):
        """Update user information for a session."""
        user_info = {"first_name": first_name, "last_name": last_name}
        response = requests.post(f"{self.base_url}/dash/update-user-info/{client_id}", json=user_info)
        response.raise_for_status()
        return response.json()

    def get_memory_usage(self):
        """Get memory usage for all sessions."""
        response = requests.get(f"{self.base_url}/dash/session-memory")
        response.raise_for_status()
        return response.json()

    def get_port_status(self):
        """Get port pool status for debugging."""
        response = requests.get(f"{self.base_url}/dash/port-status")
        response.raise_for_status()
        return response.json()

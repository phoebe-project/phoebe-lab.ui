from nicegui import ui
from client.session_api import SessionAPI


class SessionManagerUI:
    """
    A simple UI for managing sessions with a backend server.
    Allows starting new sessions, listing all sessions, and closing selected sessions.
    """

    def __init__(self):
        self.api = SessionAPI()
        
        ui.button("Start New Session", on_click=self.start_session)
        ui.button("Close Selected Session(s)", on_click=self.close_session)
        ui.button("Refresh Sessions", on_click=self.refresh_sessions)

        # Port status display
        with ui.row():
            self.port_status_label = ui.label("Port Status: Loading...")
        
        columns = [
            {'name': 'timestamp', 'label': 'Time created', 'field': 'timestamp'},
            {'name': 'client_id', 'label': 'Client ID', 'field': 'client_id'},
            {'name': 'user_display_name', 'label': 'User', 'field': 'user_display_name'},
            {'name': 'mem_used', 'label': 'Memory utilized', 'field': 'mem_used'},
            {'name': 'port', 'label': 'Port', 'field': 'port'},
        ]

        sessions = self.get_sessions()
        rows = [
            {
                'client_id': cid,
                'port': meta['port'],
                'timestamp': meta['timestamp'],
                'mem_used': meta['mem_used'],
                'user_display_name': meta.get('user_display_name', 'Not logged in')
            }
            for cid, meta in sessions.items()
        ]

        self.table = ui.table(
            columns=columns,
            rows=rows,
            row_key='client_id',
            selection='multiple',
        ).classes('w-full')
        
        # Create a timer to update memory usage and port status every 10 seconds
        self.timer = ui.timer(10.0, self.update_data)

    def get_sessions(self):
        try:
            return self.api.get_sessions()
        except Exception as e:
            ui.notify(f"Error fetching sessions: {e}", type='negative')
            return {}

    def refresh_sessions(self):
        """Refresh the session table by fetching current sessions from the server."""
        try:
            sessions = self.get_sessions()
            # Clear current rows and add fresh data
            self.table.rows.clear()
            for client_id, meta in sessions.items():
                row = {
                    'client_id': client_id,
                    'port': meta['port'],
                    'timestamp': meta['timestamp'],
                    'mem_used': f"{meta['mem_used']:2.2f} MB",
                    'user_display_name': meta.get('user_display_name', 'Not logged in')
                }
                self.table.rows.append(row)
            self.table.update()
            ui.notify("Sessions refreshed", type='positive')
        except Exception as e:
            ui.notify(f"Error refreshing sessions: {e}", type='negative')

    def update_data(self):
        """Update memory usage and port status for all sessions."""
        try:
            # Update memory usage
            memory_data = self.api.get_memory_usage()
            
            # Get fresh session data to update user info
            sessions_data = self.api.get_sessions()
            
            # Update memory usage and user info for each row
            for row in self.table.rows:
                client_id = row['client_id']
                if client_id in memory_data:
                    row['mem_used'] = f'{memory_data[client_id]:2.2f} MB'
                if client_id in sessions_data:
                    row['user_display_name'] = sessions_data[client_id].get('user_display_name', 'Not logged in')
            
            # Update port status
            port_status = self.api.get_port_status()
            self.port_status_label.text = f"Ports: {port_status['available_ports']}/{port_status['total_ports']} available"
            
            # Update the table with new values
            self.table.update()
        except Exception:
            # Silently skip errors to avoid spamming notifications
            pass

    def start_session(self):
        try:
            new_session = self.api.start_session()
            self.table.add_row(new_session)
        except Exception as e:
            ui.notify(f"Error: {e}", type='negative')

    def close_session(self):
        selected_rows = self.table.selected
        if not selected_rows:
            ui.notify("No session selected", type='warning')
            return

        try:
            for row in selected_rows:
                self.api.end_session(row['client_id'])
                ui.notify(f"Closed session {row['client_id']}")

            self.table.remove_rows(selected_rows)

        except Exception as e:
            ui.notify(f"Error closing session: {e}", type='negative')


if __name__ in {"__main__", "__mp_main__"}:
    SessionManagerUI()
    ui.run(host='0.0.0.0', port=8081)

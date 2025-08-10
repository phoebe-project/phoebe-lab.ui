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

        columns = [
            {'name': 'timestamp', 'label': 'Time created', 'field': 'timestamp'},
            {'name': 'client_id', 'label': 'Client ID', 'field': 'client_id'},
            {'name': 'mem_used', 'label': 'Memory utilized', 'field': 'mem_used'},
            {'name': 'port', 'label': 'Port', 'field': 'port'},
        ]

        sessions = self.get_sessions()
        rows = [{'client_id': cid, 'port': meta['port'], 'timestamp': meta['timestamp'], 'mem_used': meta['mem_used']} for cid, meta in sessions.items()]

        self.table = ui.table(
            columns=columns,
            rows=rows,
            row_key='client_id',
            selection='multiple',
        ).classes('w-full')
        
        # Create a timer to update memory usage every second
        self.timer = ui.timer(10.0, self.update_memory_usage)

    def get_sessions(self):
        try:
            return self.api.get_sessions()
        except Exception as e:
            ui.notify(f"Error fetching sessions: {e}", type='negative')
            return {}

    def update_memory_usage(self):
        """Update memory usage for all sessions in the table using the batch memory endpoint."""
        try:
            memory_data = self.api.get_memory_usage()
            
            # Update memory usage for each row
            for row in self.table.rows:
                client_id = row['client_id']
                if client_id in memory_data:
                    row['mem_used'] = f'{memory_data[client_id]:2.2f} MB'
            
            # Update the table with new memory values
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

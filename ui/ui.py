from nicegui import ui
import requests

client_id_label = ui.label("Client ID: Not started yet")
session_list_dropdown = ui.select([], label='Active Sessions', multiple=True, clearable=True)


def start_session():
    try:
        response = requests.post("http://localhost:8001/start-session")
        response.raise_for_status()
        data = response.json()
        client_id_label.text = f"Current client ID: {data['client_id']}"
        update_session_list()
    except Exception as e:
        ui.notify(f"Error: {e}", type='negative')


def update_session_list():
    try:
        response = requests.get("http://localhost:8001/sessions")
        response.raise_for_status()
        sessions = response.json()  # {client_id: port} dictionary
        if len(sessions) == 0:
            session_list_dropdown.options = ["No active sessions"]
            session_list_dropdown.value = None
            return
        session_list_dropdown.options = [f'{cid} (port {port})' for cid, port in sessions.items()]
        session_list_dropdown.value = session_list_dropdown.options[0]
        session_list_dropdown.update()
    except Exception as e:
        ui.notify(f"Error fetching sessions: {e}", type='negative')


def close_session():
    selected = session_list_dropdown.value
    if not selected:
        ui.notify("No session selected", type='warning')
        return

    for entry in selected:
        try:
            response = requests.post(f"http://localhost:8001/end-session/{entry.split(' ')[0]}")
            response.raise_for_status()
            ui.notify(f"Closed session {entry}")
        except Exception as e:
            ui.notify(f"Error closing session {entry}: {e}", type='negative')
        except Exception as e:
            ui.notify(f"Error closing session: {e}", type='negative')

    update_session_list()


ui.button("Start New Session", on_click=start_session)
ui.button("List All Sessions", on_click=update_session_list)
ui.button("Close Selected Session", on_click=close_session)

ui.run(host='0.0.0.0', port=8081)

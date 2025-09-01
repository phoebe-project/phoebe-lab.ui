from fastapi import APIRouter, HTTPException
from manager import session_manager


router = APIRouter()


@router.get("/dash/sessions")
def list_sessions():
    return session_manager.list_sessions()


@router.post("/dash/start-session")
def start_session():
    session = session_manager.launch_phoebe_server()
    return session


@router.post("/dash/end-session/{client_id}")
def end_session(client_id: str):
    success = session_manager.shutdown_server(client_id)
    return {"success": success}


@router.post("/dash/update-user-info/{client_id}")
def update_user_info(client_id: str, user_info: dict):
    """Update user information for a session."""
    first_name = user_info.get('first_name', '').strip()
    last_name = user_info.get('last_name', '').strip()

    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="Both first_name and last_name are required")

    success = session_manager.update_session_user_info(client_id, first_name, last_name)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "message": f"User info updated for {first_name} {last_name}"}


@router.post("/dash/session-info/{client_id}")
def session_info(client_id: str):
    info = session_manager.get_server_info(client_id)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid client ID")
    return info


@router.get('/dash/session-memory')
def session_memory_all():
    """
    Get memory usage for all active sessions.
    """
    sessions = session_manager.list_sessions()
    memory_data = {}
    for client_id in sessions.keys():
        mem_used = session_manager.get_current_memory_usage(client_id)
        if mem_used is not None:
            memory_data[client_id] = mem_used
    return memory_data


@router.post('/dash/session-memory/{client_id}')
def session_memory(client_id: str):
    mem_used = session_manager.get_current_memory_usage(client_id)
    if mem_used is None:
        raise HTTPException(status_code=404, detail="Invalid client ID")
    return {'mem_used': mem_used}


@router.get('/dash/port-status')
def port_status():
    """
    Get port pool status for debugging.
    """
    return session_manager.get_port_status()

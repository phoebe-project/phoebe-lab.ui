from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from manager import session_manager
from api.services.server_proxy import send_command


router = APIRouter()


class CommandRequest(BaseModel):
    client_id: str
    command: dict


@router.post("/start-session")
def start_session():
    session = session_manager.launch_phoebe_server()
    return session


@router.post("/send/{client_id}")
def send(client_id: str, command: dict):
    info = session_manager.get_server_info(client_id)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid client ID")

    port = info["port"]
    return send_command(port, command)


@router.post("/end-session/{client_id}")
def end_session(client_id: str):
    success = session_manager.shutdown_server(client_id)
    return {"success": success}


@router.get("/sessions")
def list_sessions():
    return session_manager.list_sessions()

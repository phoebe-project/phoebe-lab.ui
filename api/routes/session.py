from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from manager import session_manager
from api.services.server_proxy import send_command


router = APIRouter()


class CommandRequest(BaseModel):
    client_id: str
    command: dict


@router.post("/send/{client_id}")
def send(client_id: str, command: dict):
    info = session_manager.get_server_info(client_id)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid client ID")

    port = info["port"]
    return send_command(port, command)

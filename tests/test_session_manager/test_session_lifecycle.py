from manager import session_manager


def test_session_lifecycle():
    session = session_manager.launch_phoebe_server()
    client_id = session["client_id"]
    port = session["port"]

    info = session_manager.get_server_info(client_id)
    assert info is not None
    assert info["port"] == port

    sessions = session_manager.list_sessions()
    assert client_id in sessions

    result = session_manager.shutdown_server(client_id)
    assert result is True
    assert session_manager.get_server_info(client_id) is None

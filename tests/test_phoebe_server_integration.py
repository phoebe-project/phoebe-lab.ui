"""Integration test for server_proxy with actual Phoebe server."""

import sys
import os
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from manager import session_manager
from api.services.server_proxy import send_command


def test_phoebe_server_integration():
    """Test launching Phoebe server and basic message passing."""
    try:
        # Launch a Phoebe server using session manager
        session = session_manager.launch_phoebe_server()
        client_id = session['client_id']
        port = session['port']

        print(f"Launched Phoebe server: client_id={client_id}, port={port}")

        # Test basic status command
        status_command = {'cmd': 'status'}
        status_response = send_command(port=port, command=status_command)

        print(f"Status response: {status_response}")
        assert status_response is not None

        # Test Phoebe version command
        version_command = {'cmd': 'phoebe.version'}
        version_response = send_command(port=port, command=version_command)

        print(f"Version response: {version_response}")
        assert version_response is not None
        assert version_response.get('status') == 'success'
        assert 'result' in version_response
        print(f"✓ Phoebe version: {version_response['result']}")

        # Clean up - terminate the session
        try:
            session_manager.shutdown_server(client_id)
            print(f"Session {client_id} terminated")
        except Exception as e:
            print(f"Warning: Could not terminate session {client_id}: {e}")

    except Exception as e:
        pytest.fail(f"Failed to launch Phoebe server or test communication: {e}")


# def test_phoebe_phase_calculation():
#     """Test phase calculation through server."""
#     try:
#         # Launch server
#         session = session_manager.launch_phoebe_server()
#         client_id = session['client_id']
#         port = session['port']

#         print(f"Testing phase calculation with client_id={client_id}, port={port}")

#         # Setup bundle
#         setup_command = {
#             'cmd': 'import phoebe; import numpy as np; b = phoebe.default_binary()'
#         }
#         setup_response = send_command(port=port, command=setup_command)
#         print(f"Setup response: {setup_response}")

#         # Calculate phases using the parameters from the message like the UI does
#         phase_command = {
#             'cmd': 'b.to_phase',
#             'times': [0.0, 0.5, 1.0, 1.5, 2.0],
#             't0_supconj': 0.0,
#             'period': 2.0
#         }
#         phase_response = send_command(port=port, command=phase_command)
#         print(f"Phase response: {phase_response}")

#         # Verify we got a successful response with phases
#         assert phase_response is not None
#         assert phase_response.get('status') == 'success'

#         # Check if we got phases in the response (like UI expects)
#         if 'phases' in phase_response:
#             phases = phase_response['phases']
#             assert len(phases) == 5
#             print(f"✓ Calculated phases: {phases}")
#         elif 'result' in phase_response:
#             # Alternative: phases in result field
#             phases = phase_response['result']
#             print(f"✓ Calculated phases (in result): {phases}")
#         else:
#             print(f"Warning: No phases found in response: {phase_response}")

#         print("✓ Phase calculation test passed!")

#         # Clean up
#         try:
#             session_manager.terminate_session(client_id)
#             print(f"✓ Session {client_id} terminated")
#         except Exception as e:
#             print(f"Warning: Could not terminate session {client_id}: {e}")

#     except Exception as e:
#         pytest.fail(f"Phase calculation test failed: {e}")


if __name__ == '__main__':
    # Run tests manually for debugging
    print("Testing Phoebe server integration...")
    print("Using session manager to launch Phoebe server")
    print()

    try:
        print("1. Testing basic server integration...")
        test_phoebe_server_integration()
        print("✓ Basic integration test passed")
        print()

        # print("2. Testing phase calculation...")
        # test_phoebe_phase_calculation()
        # print("✓ Phase calculation test passed")
        # print()

        # print("All tests passed! ✓")

    except Exception as e:
        print(f"Test failed: {e}")
        print("Make sure the session manager is working properly")

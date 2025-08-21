"""
Common serialization utilities for JSON compatibility across the Phoebe API.

This module provides functions to convert numpy arrays and other non-JSON-serializable
objects to JSON-compatible types for communication between client and server.
"""

import numpy as np


def make_json_serializable(obj):
    """
    Convert numpy arrays and other non-serializable objects to JSON-compatible types.
    
    This function recursively processes nested structures (dicts, lists, tuples) and
    converts numpy objects to standard Python types.
    
    Parameters:
    -----------
    obj : any
        Object to be serialized (can be nested dict/list structure)
        
    Returns:
    --------
    any
        JSON-serializable equivalent of the input object
        
    Examples:
    ---------
    >>> import numpy as np
    >>> data = {'phases': np.array([0.1, 0.2, 0.3]), 'count': np.int32(42)}
    >>> serialized = make_json_serializable(data)
    >>> serialized
    {'phases': [0.1, 0.2, 0.3], 'count': 42}
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    else:
        return obj

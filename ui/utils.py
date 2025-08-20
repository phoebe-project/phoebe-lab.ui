"""
Utility functions for astronomical calculations and data transformations.
"""
import numpy as np


def time_to_phase(time, period, t0=0.0):
    """
    Convert time to orbital phase in the range [-0.5, 0.5].
    
    Parameters:
    -----------
    time : array-like
        Time values (e.g., BJD)
    period : float
        Orbital period in same units as time
    t0 : float, optional
        Reference time (epoch), default is 0.0
        
    Returns:
    --------
    array-like
        Phase values in range [-0.5, 0.5]
    """
    phase = ((time - t0) % period) / period
    # Convert from [0, 1] to [-0.5, 0.5]
    phase = np.where(phase > 0.5, phase - 1.0, phase)
    return phase


def alias_phase_for_plotting(phase, flux=None, time=None, extend_range=0.1):
    """
    Alias phase data for better visualization by extending the range.
    
    For phases in [-0.5, 0.5], this creates an extended range like [-0.6, 0.6]
    by duplicating edge data points with phase shifts of ±1.0.
    
    Parameters:
    -----------
    phase : array-like
        Phase values in range [-0.5, 0.5]
    flux : array-like, optional
        Corresponding flux/data values (will also be duplicated if provided)
    time : array-like, optional
        Corresponding time values (will also be duplicated if provided)
    extend_range : float, optional
        How much to extend beyond ±0.5, default is 0.1 (giving ±0.6 range)
        
    Returns:
    --------
    tuple
        (extended_phase, extended_flux, extended_time) based on what was provided
    """
    phase = np.asarray(phase)
    
    # Find points near the phase boundaries for aliasing
    left_boundary = -0.5 + extend_range  # e.g., -0.4
    right_boundary = 0.5 - extend_range  # e.g., 0.4
    
    # Points near +0.5 boundary (shift to left side: -1.0)
    right_edge_mask = phase > right_boundary
    left_alias_phase = phase[right_edge_mask] - 1.0
    
    # Points near -0.5 boundary (shift to right side: +1.0)
    left_edge_mask = phase < left_boundary
    right_alias_phase = phase[left_edge_mask] + 1.0
    
    # Combine original and aliased phases
    extended_phase = np.concatenate([left_alias_phase, phase, right_alias_phase])
    
    result = [extended_phase]
    
    if flux is not None:
        flux = np.asarray(flux)
        left_alias_flux = flux[right_edge_mask]
        right_alias_flux = flux[left_edge_mask]
        extended_flux = np.concatenate([left_alias_flux, flux, right_alias_flux])
        result.append(extended_flux)
    
    if time is not None:
        time = np.asarray(time)
        left_alias_time = time[right_edge_mask]
        right_alias_time = time[left_edge_mask]
        extended_time = np.concatenate([left_alias_time, time, right_alias_time])
        result.append(extended_time)
    
    return tuple(result) if len(result) > 1 else result[0]


def flux_to_magnitude(flux, zero_point=0.0):
    """
    Convert flux to magnitude.
    
    Parameters:
    -----------
    flux : array-like
        Flux values
    zero_point : float, optional
        Magnitude zero point, default is 0.0
        
    Returns:
    --------
    array-like
        Magnitude values
    """
    return -2.5 * np.log10(flux) + zero_point


def magnitude_to_flux(magnitude, zero_point=0.0):
    """
    Convert magnitude to flux.
    
    Parameters:
    -----------
    magnitude : array-like
        Magnitude values
    zero_point : float, optional
        Magnitude zero point, default is 0.0
        
    Returns:
    --------
    array-like
        Flux values
    """
    return 10**(-0.4 * (magnitude - zero_point))


def magnitude_error_to_flux_error(flux, mag_error):
    """
    Convert magnitude error to flux error.
    
    Parameters:
    -----------
    flux : array-like
        Flux values
    mag_error : array-like
        Magnitude error values
        
    Returns:
    --------
    array-like
        Flux error values
    """
    return flux * mag_error * np.log(10) / 2.5

"""
Server-Side Geographic Distance & Geofencing Validation Service.
Implements the Haversine spherical distance formula for accurate boundary checks.
"""
import math
from typing import Dict, Any, Optional
from decimal import Decimal
from .tracking_config import (
    DEFAULT_GEOFENCE_RADIUS_METERS,
    MAX_GEOFENCE_RADIUS_METERS,
    GPS_ACCURACY_WARN_THRESHOLD_METERS,
    GPS_ACCURACY_REJECT_THRESHOLD_METERS,
)


def calculate_haversine_distance(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> float:
    """
    Calculates the great-circle distance between two points on the Earth's surface
    using the Haversine formula. Returns distance in meters.
    """
    try:
        f_lat1 = float(lat1)
        f_lon1 = float(lon1)
        f_lat2 = float(lat2)
        f_lon2 = float(lon2)
    except (ValueError, TypeError):
        raise ValueError("Coordinates must be valid numbers.")

    R = 6371000.0  # Mean radius of Earth in meters

    phi1 = math.radians(f_lat1)
    phi2 = math.radians(f_lat2)
    delta_phi = math.radians(f_lat2 - f_lat1)
    delta_lambda = math.radians(f_lon2 - f_lon1)

    a = (math.sin(delta_phi / 2.0) ** 2) + (
        math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

    return round(R * c, 2)


def validate_geofence(
    user_lat: Any,
    user_lng: Any,
    user_accuracy: Optional[float],
    target_lat: Any,
    target_lng: Any,
    allowed_radius: Optional[float] = None
) -> Dict[str, Any]:
    """
    Validates whether the user's reported GPS coordinates fall within the
    target customer/hospital geofence boundary.

    Returns:
        dict:
            - is_valid (bool): True if inside allowed radius
            - distance_meters (float): Computed distance
            - allowed_radius_meters (float): Geofence radius
            - validation_status (str): 'VALID' | 'OUTSIDE_GEOFENCE' | 'NO_COORDINATES' | 'REQUIRES_REVIEW'
            - is_flagged (bool): Flagged for manager review
            - flag_reason (str): Explanation if flagged
            - error_code (str or None): Standardized error code if invalid
    """
    result = {
        'is_valid': True,
        'distance_meters': 0.0,
        'allowed_radius_meters': float(allowed_radius or DEFAULT_GEOFENCE_RADIUS_METERS),
        'validation_status': 'VALID',
        'is_flagged': False,
        'flag_reason': '',
        'error_code': None,
    }

    # Accuracy checks
    acc = float(user_accuracy) if user_accuracy is not None else 0.0
    if acc > GPS_ACCURACY_REJECT_THRESHOLD_METERS:
        result['is_valid'] = False
        result['validation_status'] = 'REQUIRES_REVIEW'
        result['is_flagged'] = True
        result['flag_reason'] = f"GPS accuracy ({acc:.1f}m) exceeds acceptable maximum ({GPS_ACCURACY_REJECT_THRESHOLD_METERS}m)."
        result['error_code'] = 'POOR_GPS_ACCURACY_REJECT'
        return result

    if acc > GPS_ACCURACY_WARN_THRESHOLD_METERS:
        result['is_flagged'] = True
        result['flag_reason'] = f"Poor GPS accuracy ({acc:.1f}m)."
        result['validation_status'] = 'REQUIRES_REVIEW'

    # Check target coordinates
    if target_lat is None or target_lng is None:
        result['is_valid'] = True
        result['validation_status'] = 'NO_COORDINATES'
        result['is_flagged'] = True
        result['flag_reason'] = "Target customer has no coordinates registered in master data."
        return result

    # Calculate actual distance
    try:
        distance = calculate_haversine_distance(user_lat, user_lng, target_lat, target_lng)
    except Exception as e:
        result['is_valid'] = False
        result['validation_status'] = 'REQUIRES_REVIEW'
        result['is_flagged'] = True
        result['flag_reason'] = f"Coordinate calculation error: {str(e)}"
        result['error_code'] = 'INVALID_COORDINATES'
        return result

    result['distance_meters'] = distance

    radius = float(allowed_radius or DEFAULT_GEOFENCE_RADIUS_METERS)
    if radius > MAX_GEOFENCE_RADIUS_METERS:
        radius = MAX_GEOFENCE_RADIUS_METERS
    result['allowed_radius_meters'] = radius

    if distance <= radius:
        if not result['is_flagged']:
            result['validation_status'] = 'VALID'
        result['is_valid'] = True
    else:
        result['is_valid'] = False
        result['validation_status'] = 'OUTSIDE_GEOFENCE'
        result['is_flagged'] = True
        deviation = distance - radius
        result['flag_reason'] = f"User is {distance:.1f}m away from target ({deviation:.1f}m outside allowed {radius:.1f}m geofence)."
        result['error_code'] = 'OUTSIDE_GEOFENCE'

    return result

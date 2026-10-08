"""
Centralized Configuration for Celldus Pharma Employee Tracking, GPS & Geofencing.
Values are configurable and can be overridden via django.conf.settings if specified.
"""
from django.conf import settings

# Geofence default settings
DEFAULT_GEOFENCE_RADIUS_METERS = getattr(settings, 'TRACKING_DEFAULT_GEOFENCE_RADIUS_METERS', 150.0)
MAX_GEOFENCE_RADIUS_METERS = getattr(settings, 'TRACKING_MAX_GEOFENCE_RADIUS_METERS', 500.0)

# GPS Accuracy validation thresholds
# Any GPS accuracy radius larger than this will be flagged as POOR_ACCURACY / REQUIRES_REVIEW
GPS_ACCURACY_WARN_THRESHOLD_METERS = getattr(settings, 'TRACKING_GPS_ACCURACY_WARN_THRESHOLD_METERS', 80.0)

# Any GPS accuracy radius larger than this will be strictly rejected
GPS_ACCURACY_REJECT_THRESHOLD_METERS = getattr(settings, 'TRACKING_GPS_ACCURACY_REJECT_THRESHOLD_METERS', 300.0)

# Visit Duration Thresholds
MIN_VISIT_DURATION_MINUTES = getattr(settings, 'TRACKING_MIN_VISIT_DURATION_MINUTES', 3)

# Implausible Travel Velocity (Teleportation / Mock GPS check: km/h)
MAX_IMPOSSIBLE_SPEED_KMH = getattr(settings, 'TRACKING_MAX_IMPOSSIBLE_SPEED_KMH', 140.0)

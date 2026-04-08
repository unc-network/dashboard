from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime


SESSION_LOGIN_AT_KEY = 'ocnes_login_at'


def normalize_aware_datetime(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def serialize_session_timestamp(value):
    value = normalize_aware_datetime(value)
    if value is None:
        return None
    return value.isoformat()


def parse_session_timestamp(value):
    if not value:
        return None
    if hasattr(value, 'tzinfo'):
        return normalize_aware_datetime(value)

    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return normalize_aware_datetime(parsed)


def get_last_activity_from_expiry(expire_date):
    return expire_date - timedelta(seconds=settings.SESSION_COOKIE_AGE)

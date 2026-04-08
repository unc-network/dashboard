"""
Cache invalidation signals for the AKIPS dashboard.
Automatically clears relevant caches when models are updated.
"""
import logging
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone

from .models import Summary, Unreachable, Trap, Status
from .session_tracking import SESSION_LOGIN_AT_KEY, serialize_session_timestamp

logger = logging.getLogger(__name__)

# Cache key constants
CACHE_KEYS = {
    'crit_card': 'crit_card_data',
    'tier_card': 'tier_card_data',
    'bldg_card': 'bldg_card_data',
    'spec_card': 'spec_card_data',
    'trap_card': 'trap_card_data',
    'crit_card_json': 'crit_card_json_data',
    'bldg_card_json': 'bldg_card_json_data',
    'spec_card_json': 'spec_card_json_data',
    'trap_card_json': 'trap_card_json_data',
    'chart_data': 'chart_data',
}


def invalidate_card_caches():
    """Clear all card caches"""
    for key in CACHE_KEYS.values():
        cache.delete(key)
    logger.debug("Cleared all card caches")


def invalidate_chart_cache():
    """Clear only chart cache"""
    cache.delete(CACHE_KEYS['chart_data'])
    logger.debug("Cleared chart cache")


@receiver(post_save, sender=Summary)
def invalidate_summary_cache(sender, instance, created=False, **kwargs):
    """Clear card caches when Summary is updated"""
    invalidate_card_caches()
    if created:
        logger.debug(f"Summary {instance.id} created - caches invalidated")
    else:
        logger.debug(f"Summary {instance.id} updated - caches invalidated")


@receiver(post_save, sender=Unreachable)
def invalidate_unreachable_cache(sender, instance, created=False, **kwargs):
    """Clear chart and card caches when Unreachable is updated"""
    invalidate_chart_cache()
    invalidate_card_caches()
    if created:
        logger.debug(f"Unreachable {instance.id} created - caches invalidated")
    else:
        logger.debug(f"Unreachable {instance.id} updated - caches invalidated")


@receiver(post_save, sender=Trap)
def invalidate_trap_cache(sender, instance, created=False, **kwargs):
    """Clear trap and chart caches when Trap is updated"""
    cache.delete(CACHE_KEYS['trap_card'])
    cache.delete(CACHE_KEYS['trap_card_json'])
    invalidate_chart_cache()
    if created:
        logger.debug(f"Trap {instance.id} created - caches invalidated")
    else:
        logger.debug(f"Trap {instance.id} updated - caches invalidated")


@receiver(post_save, sender=Status)
def invalidate_status_cache(sender, instance, created=False, **kwargs):
    """Clear chart cache when Status (e.g., UPS battery) is updated"""
    invalidate_chart_cache()
    if created:
        logger.debug(f"Status {instance.id} created - chart cache invalidated")
    else:
        logger.debug(f"Status {instance.id} updated - chart cache invalidated")


@receiver(user_logged_in)
def capture_session_login_timestamp(sender, request, user, **kwargs):
    """Persist the actual login time so session reports do not infer it from expiry."""
    if request is None:
        return

    request.session[SESSION_LOGIN_AT_KEY] = serialize_session_timestamp(timezone.now())

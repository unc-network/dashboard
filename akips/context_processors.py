"""
Template context processors for akips app.
"""
from django.conf import settings


def app_version(request):
    """
    Add the application version to the template context.
    """
    return {
        'app_version': settings.VERSION
    }

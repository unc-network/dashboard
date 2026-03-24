from django.apps import AppConfig


class AkipsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'akips'

    def ready(self):
        """Import signals when the app is ready"""
        import akips.signals  # noqa

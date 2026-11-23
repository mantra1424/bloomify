from django.apps import AppConfig


class BloomappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bloomapp'

    def ready(self):
        from . import signals  # noqa: F401 (connects the cache-clearing signal handlers)

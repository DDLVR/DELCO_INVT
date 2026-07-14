from django.apps import AppConfig


class WebConfig(AppConfig):
    name = 'web'

    def ready(self):
        from config.sqlite_compat import enable_sqlite_json_valid

        enable_sqlite_json_valid()

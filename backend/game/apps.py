from django.apps import AppConfig


class GameConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'game'
    verbose_name = 'Game'  # Shown as "GAME" in Django admin (Bets, Rounds, etc.)

    def ready(self):
        # Explicitly unregister GameSettings from admin when app is ready
        from django.contrib import admin
        from .models import GameSettings
        try:
            if admin.site.is_registered(GameSettings):
                admin.site.unregister(GameSettings)
        except:
            pass









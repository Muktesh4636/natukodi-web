"""
ASGI config for dice_game project (HTTP only; WebSockets removed).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')

application = get_asgi_application()

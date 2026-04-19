"""Template context processors for the game app."""

from django.conf import settings


def admin_ui_flags(_request):
    """Expose admin UI toggles used by ``admin/_sidebar_menu.html``."""
    return {
        'admin_sidebar_show_franchise_white_label': getattr(
            settings,
            'ADMIN_SIDEBAR_SHOW_FRANCHISE_WHITE_LABEL',
            False,
        ),
    }

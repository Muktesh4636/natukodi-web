"""
URL configuration for dice_game project.
All URLs consolidated into a single file.
"""
from django.urls import path, re_path, include

# Django admin (/admin/) is disabled at this URL — see django_admin_disabled_message in views.
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from rest_framework_simplejwt.views import TokenVerifyView
from . import views as project_views

# Import all views
from accounts import views as accounts_views
from game import views as game_views
from game import admin_views as game_admin_views

urlpatterns = [
    # APK Download endpoints (MUST come first, before everything else)
    # Using paths with file extensions that won't be caught by React routing
    # Include both with and without trailing slashes to handle Django's APPEND_SLASH
    path('gundu-ata.apk', project_views.download_apk, name='download_apk'),
    path('gundu-ata.apk/', project_views.download_apk, name='download_apk_slash'),
    path('app.apk', project_views.download_apk, name='download_apk_file'),
    path('app.apk/', project_views.download_apk, name='download_apk_file_slash'),
    path('download.apk', project_views.download_apk, name='download_apk_alt'),
    path('download.apk/', project_views.download_apk, name='download_apk_alt_slash'),
    # Also keep simple paths for convenience
    path('apk', project_views.download_apk, name='download_apk_simple'),
    path('apk/', project_views.download_apk, name='download_apk_simple_slash'),
    path('download-apk', project_views.download_apk, name='download_apk_dash'),
    path('download-apk/', project_views.download_apk, name='download_apk_dash_slash'),
    
    # /admin/ — no Django DB admin here (no redirect; static message only)
    re_path(r'^admin(?:/.*)?$', project_views.django_admin_disabled_message),
    # Media files (explicit so uploads like deposit_screenshots are always served by Django)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    path('api/', project_views.api_root, name='api_root'),
    path('api/health/', project_views.health, name='health'),
    path('api/status/', project_views.api_status, name='api_status'),
    path('api/time/', project_views.time_now, name='time_now'),
    # Maintenance status (public; works even when maintenance is on)
    path('api/maintenance/status/', project_views.maintenance_status, name='maintenance_status'),
    # Standalone system health dashboard (separate from admin panel UI)
    path('system-health/', game_admin_views.system_health_dashboard, name='system_health_dashboard'),
    path('system-health/data/', game_admin_views.system_health_data, name='system_health_data'),
    
    # Loading time endpoint (no authentication)
    path('api/loading-time/', accounts_views.loading_time, name='loading_time'),

    # Public support contacts (help center)
    path('api/support/contacts/', project_views.support_contacts, name='support_contacts'),
    path('api/cricket/live-events/', project_views.live_cricket_events, name='live_cricket_events'),
    
    # Auth endpoints (api/auth/)
    path('api/auth/register/', accounts_views.register, name='register'),
    path('api/auth/login/', accounts_views.login, name='login'),
    path('api/auth/otp/send/', accounts_views.send_otp, name='send_otp'),
    path('api/auth/otp/verify-login/', accounts_views.verify_otp_login, name='verify_otp_login'),
    path('api/auth/token/refresh/', accounts_views.SingleSessionTokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/auth/profile/', accounts_views.profile, name='profile'),
    path('api/auth/profile/photo/', accounts_views.update_profile_photo, name='update_profile_photo'),
    path('api/auth/referral-data/', accounts_views.referral_data, name='referral_data'),
    path('api/auth/wallet/', accounts_views.WalletView.as_view(), name='wallet'),
    path('api/auth/transactions/', accounts_views.TransactionList.as_view(), name='transactions'),
    path('api/auth/extract-utr/', accounts_views.extract_utr, name='extract_utr'),
    path('api/auth/process-screenshot/', accounts_views.process_payment_screenshot, name='process_payment_screenshot'),
    path('api/auth/deposits/initiate/', accounts_views.initiate_deposit, name='initiate_deposit'),
    path('api/auth/deposits/upload-proof/', accounts_views.upload_deposit_proof, name='upload_deposit_proof'),
    path('api/auth/deposits/submit-utr/', accounts_views.submit_utr, name='submit_utr'),
    path('api/auth/deposits/mine/', accounts_views.my_deposit_requests, name='my_deposit_requests'),
    path('api/auth/deposits/pending/', accounts_views.pending_deposit_requests, name='pending_deposit_requests'),
    path('api/auth/deposits/<int:pk>/approve/', accounts_views.approve_deposit_request, name='approve_deposit_request'),
    path('api/auth/deposits/<int:pk>/reject/', accounts_views.reject_deposit_request, name='reject_deposit_request'),
    path('api/auth/withdraws/initiate/', accounts_views.initiate_withdraw, name='initiate_withdraw'),
    path('api/auth/withdraws/mine/', accounts_views.my_withdraw_requests, name='my_withdraw_requests'),
    path('api/auth/payment-methods/', accounts_views.get_payment_methods, name='get_payment_methods'),
    path('api/auth/bank-details/', accounts_views.my_bank_details, name='my_bank_details'),
    path('api/auth/bank-details/<int:pk>/', accounts_views.bank_detail_action, name='bank_detail_action'),
    path('api/auth/daily-reward/', accounts_views.daily_reward, name='daily_reward'),
    path('api/auth/daily-reward/history/', accounts_views.daily_reward_history, name='daily_reward_history'),
    path('api/auth/lucky-draw/', accounts_views.lucky_draw, name='lucky_draw'),
    path('api/auth/leaderboard/', accounts_views.leaderboard, name='leaderboard'),
    path('api/auth/register-fcm-token/', accounts_views.register_fcm_token, name='register_fcm_token'),
    path('api/auth/password/reset/', accounts_views.reset_password, name='reset_password'),
    path('api/auth/password/change/', accounts_views.change_password, name='change_password'),
    
    # APK Download via API (guaranteed to work since API routes come before React)
    path('api/download/apk/', project_views.download_apk, name='api_download_apk'),
    path('api/apk/', project_views.download_apk, name='api_apk'),

    # White-label lead capture (public)
    path('api/whitelabel/lead/', project_views.white_label_lead, name='white_label_lead'),
    # Client payments: ending payment (pending commission) per user — for client-payments app
    path('api/client-payments/ending-payment/<int:user_id>/', game_views.ending_payment_for_user, name='ending_payment_for_user'),
    # Game settings API temporarily removed — see temporary_deleted/
    # Game endpoints (api/game/)
    path('api/game/', include('game.urls')),
    
    # Game admin endpoints (game-admin/)
    # No trailing slash must redirect before React catch-all (otherwise SPA loads)
    path('game-admin', RedirectView.as_view(url='/game-admin/', permanent=False), name='game_admin_root_noslash'),
    # Base game-admin path - redirect to login or dashboard based on auth status
    path('game-admin/', game_admin_views.admin_login, name='game_admin_root'),
    path('game-admin/login/', game_admin_views.admin_login, name='admin_login'),
    path('game-admin/logout/', game_admin_views.admin_logout, name='admin_logout'),
    path('game-admin/profile/', game_admin_views.admin_profile, name='admin_profile'),
    path('game-admin/forgot-password/', game_admin_views.admin_forgot_password, name='admin_forgot_password'),
    path('game-admin/ping/', game_admin_views.admin_ping, name='admin_ping'),
    # Redirect game-admin/admin/ -> Django admin (view DB tables)
    path('game-admin/admin/', RedirectView.as_view(url='/admin/', permanent=False), name='game_admin_to_django_admin'),
    path('game-admin/dashboard/', game_admin_views.admin_dashboard, name='admin_dashboard'),
    path('game-admin/recent-rounds/', game_admin_views.recent_rounds, name='recent_rounds'),
    path('game-admin/round/<str:round_id>/', game_admin_views.round_details, name='round_details'),
    path('game-admin/user/<int:user_id>/', game_admin_views.user_details, name='user_details'),
    path('game-admin/testing-dashboard/', game_admin_views.testing_dashboard, name='testing_dashboard'),
    path('game-admin/testing-dashboard/start/', game_admin_views.start_simulation, name='start_simulation'),
    path('game-admin/testing-dashboard/stop/', game_admin_views.stop_simulation, name='stop_simulation'),
    path('game-admin/testing-dashboard/status/', game_admin_views.simulation_status, name='simulation_status'),
    path('game-admin/all-bets/', game_admin_views.all_bets, name='all_bets'),
    path('game-admin/wallets/', game_admin_views.wallets, name='wallets'),
    path('game-admin/deposit-requests/', game_admin_views.deposit_requests, name='deposit_requests'),
    path('game-admin/deposit-requests/check-new/', game_admin_views.check_new_deposit_requests, name='check_new_deposit_requests'),
    path('game-admin/deposit-requests/<int:pk>/approve/', game_admin_views.approve_deposit, name='approve_deposit'),
    path('game-admin/deposit-requests/<int:pk>/reject/', game_admin_views.reject_deposit, name='reject_deposit'),
    path('game-admin/deposit-requests/<int:pk>/edit-amount/', game_admin_views.edit_deposit_amount, name='edit_deposit_amount'),
    path('game-admin/withdraw-requests/', game_admin_views.withdraw_requests, name='withdraw_requests'),
    path('game-admin/withdraw-requests/check-new/', game_admin_views.check_new_withdraw_requests, name='check_new_withdraw_requests'),
    path('game-admin/withdraw-requests/<int:pk>/approve/', game_admin_views.approve_withdraw, name='approve_withdraw'),
    path('game-admin/withdraw-requests/<int:pk>/complete-payment/', game_admin_views.complete_withdraw_payment, name='complete_withdraw_payment'),
    path('game-admin/withdraw-requests/<int:pk>/reject/', game_admin_views.reject_withdraw, name='reject_withdraw'),
    path('game-admin/reports/', game_admin_views.transactions, name='admin_transactions'),
    path('game-admin/dashboard-data/', game_admin_views.admin_dashboard_data, name='admin_dashboard_data'),
    path('game-admin/system-health/', RedirectView.as_view(url='/system-health/', permanent=False), name='system_health_dashboard_admin_redirect'),
    path('game-admin/system-health/data/', RedirectView.as_view(url='/system-health/data/', permanent=False), name='system_health_data_admin_redirect'),
    path('game-admin/players-list/', game_admin_views.manage_players, name='manage_players'),
    path('game-admin/players/', game_admin_views.players, name='players'),
    path('game-admin/players/assign-worker/', game_admin_views.assign_worker, name='assign_worker'),
    path('game-admin/game-settings/', game_admin_views.game_settings, name='game_settings'),
    path('game-admin/help-center/', game_admin_views.help_center, name='help_center'),
    path('game-admin/white-label/', game_admin_views.white_label_leads, name='white_label_leads'),
    path('game-admin/maintenance-toggle/', game_admin_views.maintenance_toggle, name='maintenance_toggle'),
    path('game-admin/logout-all-sessions/', game_admin_views.logout_all_sessions, name='logout_all_sessions'),
    path('game-admin/worker-management/', game_admin_views.admin_management, name='admin_management'),
    path('game-admin/worker-management/create/', game_admin_views.create_admin, name='create_admin'),
    path('game-admin/worker-management/<int:admin_id>/toggle-active/', game_admin_views.toggle_admin_status, name='toggle_admin_status'),
    path('game-admin/worker-management/edit/<int:admin_id>/', game_admin_views.edit_admin, name='edit_admin'),
    path('game-admin/worker-management/delete/<int:admin_id>/', game_admin_views.delete_admin, name='delete_admin'),
    path('game-admin/franchise-balance/', game_admin_views.franchise_balance, name='franchise_balance'),
    path('game-admin/franchise-balance/details/<int:admin_id>/', game_admin_views.franchise_admin_details, name='franchise_admin_details'),
    path('game-admin/franchise-balance/details/<int:admin_id>/players/', game_admin_views.franchise_admin_players, name='franchise_admin_players'),
    path('game-admin/franchise-balance/edit/<int:admin_id>/', game_admin_views.edit_franchise_admin, name='edit_franchise_admin'),
    path('game-admin/franchise-balance/create/', game_admin_views.create_franchise_admin, name='create_franchise_admin'),
    
    # Payment Methods
    path('game-admin/payment-methods/', game_admin_views.payment_methods, name='payment_methods'),
    path('game-admin/payment-methods/create/', game_admin_views.create_payment_method, name='create_payment_method'),
    path('game-admin/payment-methods/<int:pk>/edit/', game_admin_views.edit_payment_method, name='edit_payment_method'),
    path('game-admin/payment-methods/<int:pk>/delete/', game_admin_views.delete_payment_method, name='delete_payment_method'),
    path('game-admin/payment-methods/<int:pk>/toggle/', game_admin_views.toggle_payment_method, name='toggle_payment_method'),
    
    # Serve React static assets (assets/*)
    re_path(r'^assets/.*$', project_views.serve_react_app, name='react_assets'),
    
    # Root path - public website landing page
    path('', project_views.home, name='root'),
    
    # Catch-all route for React app (must be last)
    # This will serve the React app for all routes not matched above
    # Updated regex to properly match all paths except API/admin/static/media/ws/assets/apk/download paths
    # Handles potential double slashes and varying prefixes
    # Explicitly exclude download paths and .apk files
    # Exclude game-admin with or without trailing slash so /game-admin never hits the SPA
    re_path(
        r'^(?!/?api/)(?!/?admin(?:/|$))(?!/?game-admin(?:/|$))(?!/?static/)(?!/?media/)(?!/?ws/)(?!/?assets/)(?!apk$)(?!download-apk$)(?!.*\.apk$).*$',
        project_views.serve_react_app,
        name='react_app',
    ),
]

# Serve static and media files (always in development, only static in production)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

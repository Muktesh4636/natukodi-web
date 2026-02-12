"""
URL configuration for dice_game project.
All URLs consolidated into a single file.
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from . import views as project_views

# Import all views
from accounts import views as accounts_views
from game import views as game_views
from game import admin_views as game_admin_views

urlpatterns = [
    # Admin (must come before catch-all)
    path('admin/', admin.site.urls),
    path('api/', project_views.api_root, name='api_root'),
    
    # Auth endpoints (api/auth/)
    path('api/auth/register/', accounts_views.register, name='register'),
    path('api/auth/login/', accounts_views.login, name='login'),
    path('api/auth/otp/send/', accounts_views.send_otp, name='send_otp'),
    path('api/auth/otp/verify-login/', accounts_views.verify_otp_login, name='verify_otp_login'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/auth/profile/', accounts_views.profile, name='profile'),
    path('api/auth/profile/photo/', accounts_views.update_profile_photo, name='update_profile_photo'),
    path('api/auth/referral-data/', accounts_views.referral_data, name='referral_data'),
    path('api/auth/wallet/', accounts_views.wallet, name='wallet'),
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
    
    # Game endpoints (api/game/)
    path('api/game/', include('game.urls')),
    
    # Game admin endpoints (game-admin/)
    # Base game-admin path - redirect to login or dashboard based on auth status
    path('game-admin/', game_admin_views.admin_login, name='game_admin_root'),
    path('game-admin/login/', game_admin_views.admin_login, name='admin_login'),
    path('game-admin/logout/', game_admin_views.admin_logout, name='admin_logout'),
    path('game-admin/dashboard/', game_admin_views.admin_dashboard, name='admin_dashboard'),
    path('game-admin/dice-control/', game_admin_views.dice_control, name='dice_control'),
    path('game-admin/recent-rounds/', game_admin_views.recent_rounds, name='recent_rounds'),
    path('game-admin/round/<str:round_id>/', game_admin_views.round_details, name='round_details'),
    path('game-admin/user/<int:user_id>/', game_admin_views.user_details, name='user_details'),
    path('game-admin/all-bets/', game_admin_views.all_bets, name='all_bets'),
    path('game-admin/wallets/', game_admin_views.wallets, name='wallets'),
    path('game-admin/deposit-requests/', game_admin_views.deposit_requests, name='deposit_requests'),
    path('game-admin/deposit-requests/check-new/', game_admin_views.check_new_deposit_requests, name='check_new_deposit_requests'),
    path('game-admin/deposit-requests/<int:pk>/approve/', game_admin_views.approve_deposit, name='approve_deposit'),
    path('game-admin/deposit-requests/<int:pk>/reject/', game_admin_views.reject_deposit, name='reject_deposit'),
    path('game-admin/withdraw-requests/', game_admin_views.withdraw_requests, name='withdraw_requests'),
    path('game-admin/withdraw-requests/check-new/', game_admin_views.check_new_withdraw_requests, name='check_new_withdraw_requests'),
    path('game-admin/withdraw-requests/<int:pk>/approve/', game_admin_views.approve_withdraw, name='approve_withdraw'),
    path('game-admin/withdraw-requests/<int:pk>/reject/', game_admin_views.reject_withdraw, name='reject_withdraw'),
    path('game-admin/reports/', game_admin_views.transactions, name='admin_transactions'),
    path('game-admin/dashboard-data/', game_admin_views.admin_dashboard_data, name='admin_dashboard_data'),
    path('game-admin/set-dice/', game_admin_views.set_dice_result_view, name='set_dice_result_view'),
    path('game-admin/set-individual-dice/', game_admin_views.set_individual_dice_view, name='set_individual_dice_view'),
    path('game-admin/toggle-dice-mode/', game_admin_views.toggle_dice_mode, name='toggle_dice_mode'),
    path('game-admin/players-list/', game_admin_views.manage_players, name='manage_players'),
    path('game-admin/players/', game_admin_views.players, name='players'),
    path('game-admin/players/assign-worker/', game_admin_views.assign_worker, name='assign_worker'),
    path('game-admin/game-settings/', game_admin_views.game_settings, name='game_settings'),
    path('game-admin/admin-management/', game_admin_views.admin_management, name='admin_management'),
    path('game-admin/admin-management/create/', game_admin_views.create_admin, name='create_admin'),
    path('game-admin/admin-management/edit/<int:admin_id>/', game_admin_views.edit_admin, name='edit_admin'),
    path('game-admin/admin-management/delete/<int:admin_id>/', game_admin_views.delete_admin, name='delete_admin'),
    
    # Payment Methods
    path('game-admin/payment-methods/', game_admin_views.payment_methods, name='payment_methods'),
    path('game-admin/payment-methods/create/', game_admin_views.create_payment_method, name='create_payment_method'),
    path('game-admin/payment-methods/<int:pk>/edit/', game_admin_views.edit_payment_method, name='edit_payment_method'),
    path('game-admin/payment-methods/<int:pk>/delete/', game_admin_views.delete_payment_method, name='delete_payment_method'),
    path('game-admin/payment-methods/<int:pk>/toggle/', game_admin_views.toggle_payment_method, name='toggle_payment_method'),
    
    # Serve React static assets (assets/*)
    re_path(r'^assets/.*$', project_views.serve_react_app, name='react_assets'),
    
    # Root path - serve React app (must come before catch-all)
    path('', project_views.serve_react_app, name='root'),
    
    # Catch-all route for React app (must be last)
    # This will serve the React app for all routes not matched above
    # Updated regex to properly match all paths except API/admin/static/media/ws/assets
    # Handles potential double slashes and varying prefixes
    re_path(r'^(?!/?api/|/?admin/|/?game-admin/|/?static/|/?media/|/?ws/|/?assets/).*', project_views.serve_react_app, name='react_app'),
]

# Serve static and media files (always in development, only static in production)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

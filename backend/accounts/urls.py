from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('otp/send/', views.send_otp, name='send_otp'),
    path('otp/verify-login/', views.verify_otp_login, name='verify_otp_login'),
    path('profile/', views.profile, name='profile'),
    path('wallet/', views.WalletView.as_view(), name='wallet'),
    path('transactions/', views.TransactionList.as_view(), name='transactions'),
    path('extract-utr/', views.extract_utr, name='extract_utr'),
    path('process-screenshot/', views.process_payment_screenshot, name='process_payment_screenshot'),
    path('deposits/initiate/', views.initiate_deposit, name='initiate_deposit'),
    path('deposits/upload-proof/', views.upload_deposit_proof, name='upload_deposit_proof'),
    path('deposits/mine/', views.my_deposit_requests, name='my_deposit_requests'),
    path('deposits/pending/', views.pending_deposit_requests, name='pending_deposit_requests'),
    path('deposits/<int:pk>/approve/', views.approve_deposit_request, name='approve_deposit_request'),
    path('deposits/<int:pk>/reject/', views.reject_deposit_request, name='reject_deposit_request'),
    path('withdraws/initiate/', views.initiate_withdraw, name='initiate_withdraw'),
    path('withdraws/mine/', views.my_withdraw_requests, name='my_withdraw_requests'),
    path('bank-details/', views.my_bank_details, name='my_bank_details'),
    path('bank-details/<int:pk>/', views.bank_detail_action, name='bank_detail_action'),
    path('daily-reward/', views.daily_reward, name='daily_reward'),
    path('daily-reward/history/', views.daily_reward_history, name='daily_reward_history'),
    path('lucky-draw/', views.lucky_draw, name='lucky_draw'),
]





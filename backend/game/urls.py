from django.urls import path
from . import views

urlpatterns = [
    path('round/', views.current_round, name='current_round'),
    path('round/start-time/', views.round_start_time, name='round_start_time'),
    path('round/<str:round_id>/bets/', views.round_bets, name='round_bets'),
    path('round/bets/', views.round_bets, name='round_bets_current'),
    path('round/<str:round_id>/exposure/', views.round_exposure, name='round_exposure'),
    path('round/exposure/', views.round_exposure, name='round_exposure_current'),
    path('bet/', views.place_bet, name='place_bet'),
    path('bet', views.place_bet, name='place_bet_no_slash'),
    path('bet/<int:number>/', views.remove_bet, name='remove_bet'),
    path('bet/id/<int:bet_id>/', views.remove_bet_by_id, name='remove_bet_by_id'),
    path('bet/last/', views.remove_last_bet, name='remove_last_bet'),
    path('bets/', views.my_bets, name='my_bets'),
    path('user-bets-summary/', views.user_bets_summary, name='user_bets_summary'),
    path('prediction/', views.submit_prediction, name='submit_prediction'),
    path('round/<str:round_id>/predictions/', views.round_predictions, name='round_predictions'),
    path('round/predictions/', views.round_predictions, name='round_predictions_current'),
    path('betting-history/', views.betting_history, name='betting_history'),
    path('version/', views.app_version, name='app_version'),
    path('frequency/', views.dice_frequency, name='dice_frequency'),
    path('frequency/<str:round_id>/', views.dice_frequency, name='dice_frequency_by_id'),
    path('last-round-results/', views.last_round_results, name='last_round_results'),
    path('last_round_results/', views.last_round_results, name='last_round_results_underscore'),
    path('recent-round-results/', views.recent_round_results, name='recent_round_results'),
    path('user-round-results/<str:round_id>/', views.round_results, name='round_results'),
    path('winning-results/', views.winning_results, name='winning_results_current'),
    path('winning-results', views.winning_results, name='winning_results_current_no_slash'),
    path('winning-results/<str:round_id>/', views.winning_results, name='winning_results'),
    path('winning-results/<str:round_id>', views.winning_results, name='winning_results_no_slash'),
    path('results/<str:round_id>/', views.round_results, name='winning_results_alias'),
    path('stats/', views.game_stats, name='game_stats'),
    # game settings API temporarily removed — see temporary_deleted/
    path('max-bet/', views.max_bet, name='max_bet'),
    path('settings/sound/', views.user_sound_settings, name='user_sound_settings'),
    
    # Admin Probability Settings
    path('admin/mega-spin-prob/', views.admin_mega_spin_prob, name='admin_mega_spin_prob_global'),
    path('admin/mega-spin-prob/<int:user_id>/', views.admin_mega_spin_prob, name='admin_mega_spin_prob_user'),
    path('admin/daily-reward-prob/', views.admin_daily_reward_prob, name='admin_daily_reward_prob_global'),
    path('admin/daily-reward-prob/<int:user_id>/', views.admin_daily_reward_prob, name='admin_daily_reward_prob_user'),
]


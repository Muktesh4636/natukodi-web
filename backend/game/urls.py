from django.urls import path, re_path
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
    path('bets/mine/', views.my_bets, name='my_bets_mine'),
    path('user-bets-summary/', views.user_bets_summary, name='user_bets_summary'),
    path('betting-history/', views.betting_history, name='betting_history'),
    path('version/', views.app_version, name='app_version'),
    path('frequency/', views.dice_frequency, name='dice_frequency'),
    path('frequency/<str:round_id>/', views.dice_frequency, name='dice_frequency_by_id'),
    path('stats/', views.game_stats, name='game_stats'),
    # game settings API temporarily removed — see temporary_deleted/
    path('max-bet/', views.max_bet, name='max_bet'),
    path('settings/sound/', views.user_sound_settings, name='user_sound_settings'),
    
    # Admin Probability Settings
    path('admin/mega-spin-prob/', views.admin_mega_spin_prob, name='admin_mega_spin_prob_global'),
    path('admin/mega-spin-prob/<int:user_id>/', views.admin_mega_spin_prob, name='admin_mega_spin_prob_user'),
    path('admin/daily-reward-prob/', views.admin_daily_reward_prob, name='admin_daily_reward_prob_global'),
    path('admin/daily-reward-prob/<int:user_id>/', views.admin_daily_reward_prob, name='admin_daily_reward_prob_user'),

    # Cock fight: Cock 1 / Cock 2 / Draw (legacy paths kept as meron-wala/*)
    path('meron-wala/bet/', views.place_meron_wala_bet, name='place_meron_wala_bet'),
    path('meron-wala/bets/mine/', views.my_cock_fight_bets, name='my_cock_fight_bets'),
    path('meron-wala/info/', views.cock_fight_info, name='cock_fight_info'),
    path(
        'meron-wala/latest-round-video/',
        views.meron_wala_latest_round_video,
        name='meron_wala_latest_round_video',
    ),
    re_path(
        r'^meron-wala/hls/(?P<signed_token>[^/]+)/(?P<file_path>.+)$',
        views.cockfight_hls_serve,
        name='cockfight_hls_serve',
    ),
    path('meron-wala/settle/', views.settle_cock_fight, name='settle_cock_fight'),
    path('meron-wala/admin/settle-round/', views.settle_meron_wala_round, name='settle_meron_wala_round'),
]


from django.urls import path
from . import views

urlpatterns = [
    path('round/', views.current_round, name='current_round'),
    path('round/<str:round_id>/bets/', views.round_bets, name='round_bets'),
    path('round/bets/', views.round_bets, name='round_bets_current'),
    path('round/<str:round_id>/exposure/', views.round_exposure, name='round_exposure'),
    path('round/exposure/', views.round_exposure, name='round_exposure_current'),
    path('bet/', views.place_bet, name='place_bet'),
    path('bet', views.place_bet, name='place_bet_no_slash'),
    path('bet/<int:number>/', views.remove_bet, name='remove_bet'),
    path('bet/last/', views.remove_last_bet, name='remove_last_bet'),
    path('bets/', views.my_bets, name='my_bets'),
    path('prediction/', views.submit_prediction, name='submit_prediction'),
    path('round/<str:round_id>/predictions/', views.round_predictions, name='round_predictions'),
    path('round/predictions/', views.round_predictions, name='round_predictions_current'),
    path('betting-history/', views.betting_history, name='betting_history'),
    path('user-round-results/<str:round_id>/', views.round_results_api, name='round_results'),
    path('winning-results/', views.winning_results, name='winning_results_current'),
    path('winning-results/<str:round_id>/', views.winning_results, name='winning_results'),
    path('results/<str:round_id>/', views.winning_results, name='winning_results_alias'),
    path('set-dice/', views.set_dice_result, name='set_dice_result'),
    path('dice-mode/', views.dice_mode, name='dice_mode'),
    path('stats/', views.game_stats, name='game_stats'),
    path('settings/', views.game_settings_api, name='game_settings_api'),
    path('settings', views.game_settings_api, name='game_settings_api_no_slash'),
]


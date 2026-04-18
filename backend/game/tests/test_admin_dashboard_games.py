"""Dashboard JSON includes per-game stats (Gunduata, Cricket, Cock fight)."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class AdminDashboardGamesJsonTests(TestCase):
    def test_dashboard_data_includes_games_structure(self):
        admin = User.objects.create_user(
            username='dash_super',
            password='secret1234',
            is_staff=True,
            is_superuser=True,
        )
        client = Client()
        client.force_login(admin)
        response = client.get('/game-admin/dashboard-data/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('games', data)
        games = data['games']
        for key in ('gunduata', 'cricket', 'cockfight'):
            self.assertIn(key, games, msg=f'missing games.{key}')
            g = games[key]
            self.assertIn('label', g)
            for period in ('period', 'today', 'yesterday'):
                self.assertIn(period, g)
                block = g[period]
                self.assertIn('bets_count', block)
                self.assertIn('stake_amount', block)
                self.assertIn('payout_amount', block)
                self.assertIn('profit', block)
            for period in ('today', 'yesterday'):
                self.assertIn('active_bettors', games[key][period])

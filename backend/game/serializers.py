from rest_framework import serializers
from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction
from accounts.serializers import UserSerializer


class GameRoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameRound
        fields = '__all__'
        read_only_fields = ['round_id', 'start_time', 'betting_close_time', 'result_time', 'end_time']


class BetSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    round = GameRoundSerializer(read_only=True)

    class Meta:
        model = Bet
        fields = '__all__'
        read_only_fields = ['payout_amount', 'is_winner', 'created_at']


class CreateBetSerializer(serializers.Serializer):
    number = serializers.IntegerField(min_value=1, max_value=6)
    chip_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class DiceResultSerializer(serializers.ModelSerializer):
    round = GameRoundSerializer(read_only=True)

    class Meta:
        model = DiceResult
        fields = '__all__'
        read_only_fields = ['set_at']


class GameSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameSettings
        fields = '__all__'
        read_only_fields = ['updated_at']


class BettingHistorySerializer(serializers.ModelSerializer):
    """Simplified serializer for betting history - excludes user, simplifies round data"""
    round = serializers.SerializerMethodField()
    
    class Meta:
        model = Bet
        fields = ['id', 'round', 'number', 'chip_amount', 'payout_amount', 'is_winner', 'created_at']
        read_only_fields = ['id', 'payout_amount', 'is_winner', 'created_at']
    
    def get_round(self, obj):
        """Return simplified round data"""
        return {
            'round_id': obj.round.round_id,
            'status': obj.round.status,
            'dice_result': obj.round.dice_result,
            'created_at': obj.round.start_time.isoformat() if obj.round.start_time else None
        }


class RoundPredictionSerializer(serializers.ModelSerializer):
    """Serializer for round predictions"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = RoundPrediction
        fields = ['id', 'user', 'round', 'number', 'is_correct', 'created_at']
        read_only_fields = ['id', 'is_correct', 'created_at']


class CreatePredictionSerializer(serializers.Serializer):
    """Serializer for creating a prediction"""
    number = serializers.IntegerField(min_value=1, max_value=6)









from rest_framework import serializers
from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction, UserSoundSetting, MegaSpinProbability, DailyRewardProbability
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


class UserSoundSettingSerializer(serializers.ModelSerializer):
    """Serializer for user sound settings"""
    class Meta:
        model = UserSoundSetting
        fields = ['background_music_volume', 'is_muted', 'updated_at']
        read_only_fields = ['updated_at']

    def validate_background_music_volume(self, value):
        if not 0.0 <= value <= 1.0:
            raise serializers.ValidationError("Volume must be between 0.0 and 1.0")
        return value


class MegaSpinProbabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MegaSpinProbability
        fields = ['prob_1', 'prob_2', 'prob_3', 'prob_4', 'prob_5', 'prob_6', 'prob_7', 'prob_8', 'updated_at']
        read_only_fields = ['updated_at']

    def validate(self, data):
        # Ensure total probability equals 100
        total = sum([data.get(f'prob_{i}', getattr(self.instance, f'prob_{i}', 12.5)) for i in range(1, 9)])
        if abs(total - 100.0) > 0.01:
            raise serializers.ValidationError("Total probability must equal 100%")
        return data


class DailyRewardProbabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyRewardProbability
        fields = ['prob_low', 'prob_medium', 'prob_high', 'prob_mega', 'updated_at']
        read_only_fields = ['updated_at']

    def validate(self, data):
        # Ensure total probability equals 100
        total = data.get('prob_low', getattr(self.instance, 'prob_low', 70.0)) + \
                data.get('prob_medium', getattr(self.instance, 'prob_medium', 20.0)) + \
                data.get('prob_high', getattr(self.instance, 'prob_high', 9.0)) + \
                data.get('prob_mega', getattr(self.instance, 'prob_mega', 1.0))
        if abs(total - 100.0) > 0.01:
            raise serializers.ValidationError("Total probability must equal 100%")
        return data









from django.contrib import admin
from django import forms
from django.utils.html import format_html
from .models import GameRound, Bet, DiceResult, GameSettings, UserSoundSetting, MegaSpinProbability, DailyRewardProbability


@admin.register(GameRound)
class GameRoundAdmin(admin.ModelAdmin):
    list_display = ['round_id', 'status', 'dice_result', 'start_time', 'total_bets', 'total_amount']
    list_filter = ['status', 'start_time']
    search_fields = ['round_id']
    readonly_fields = ['start_time', 'betting_close_time', 'result_time', 'end_time']
    date_hierarchy = 'start_time'


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ['user', 'round', 'number', 'chip_amount', 'payout_amount', 'is_winner', 'created_at']
    list_filter = ['is_winner', 'created_at', 'round']
    search_fields = ['user__username', 'round__round_id']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(DiceResult)
class DiceResultAdmin(admin.ModelAdmin):
    list_display = ['round', 'result', 'set_by', 'set_at']
    list_filter = ['set_at']
    search_fields = ['round__round_id']
    readonly_fields = ['set_at']
    date_hierarchy = 'set_at'


class GameSettingsAdminForm(forms.ModelForm):
    """Custom form for GameSettings with validation"""
    
    class Meta:
        model = GameSettings
        fields = ['key', 'value', 'description']
    
    def clean_value(self):
        value = self.cleaned_data.get('value')
        key = self.cleaned_data.get('key')
        
        # Validate numeric settings
        numeric_keys = [
            'BETTING_CLOSE_TIME', 'DICE_ROLL_TIME', 'DICE_RESULT_TIME', 'ROUND_END_TIME',
            'BETTING_DURATION', 'RESULT_SELECTION_DURATION', 
            'RESULT_DISPLAY_DURATION', 'TOTAL_ROUND_DURATION',
            'RESULT_ANNOUNCE_TIME'
        ]
        
        if key in numeric_keys:
            try:
                int_value = int(value)
                if int_value < 0:
                    raise forms.ValidationError(f"{key} must be a positive number")
                
                # Validate timing relationships (exclude current instance if editing)
                instance = self.instance
                
                if key == 'BETTING_CLOSE_TIME':
                    # BETTING_CLOSE_TIME should be less than DICE_RESULT_TIME
                    try:
                        dice_result_setting = GameSettings.objects.exclude(pk=instance.pk if instance else None).get(key='DICE_RESULT_TIME')
                        if int_value >= int(dice_result_setting.value):
                            raise forms.ValidationError(
                                f"Betting close time must be less than dice result time (currently {dice_result_setting.value})"
                            )
                    except GameSettings.DoesNotExist:
                        pass
                
                if key == 'DICE_ROLL_TIME':
                    # DICE_ROLL_TIME should be less than DICE_RESULT_TIME
                    try:
                        dice_result_setting = GameSettings.objects.exclude(pk=instance.pk if instance else None).get(key='DICE_RESULT_TIME')
                        if int_value >= int(dice_result_setting.value):
                            raise forms.ValidationError(
                                f"Dice roll time must be less than dice result time (currently {dice_result_setting.value})"
                            )
                    except GameSettings.DoesNotExist:
                        pass
                
                if key == 'DICE_RESULT_TIME':
                    # DICE_RESULT_TIME should be less than ROUND_END_TIME
                    try:
                        round_end_setting = GameSettings.objects.exclude(pk=instance.pk if instance else None).get(key='ROUND_END_TIME')
                        if int_value >= int(round_end_setting.value):
                            raise forms.ValidationError(
                                f"Dice result time must be less than round end time (currently {round_end_setting.value})"
                            )
                    except GameSettings.DoesNotExist:
                        pass
                    # DICE_RESULT_TIME should be greater than BETTING_CLOSE_TIME
                    try:
                        betting_close_setting = GameSettings.objects.exclude(pk=instance.pk if instance else None).get(key='BETTING_CLOSE_TIME')
                        if int_value <= int(betting_close_setting.value):
                            raise forms.ValidationError(
                                f"Dice result time must be greater than betting close time (currently {betting_close_setting.value})"
                            )
                    except GameSettings.DoesNotExist:
                        pass
                    # DICE_RESULT_TIME should be greater than DICE_ROLL_TIME
                    try:
                        dice_roll_setting = GameSettings.objects.exclude(pk=instance.pk if instance else None).get(key='DICE_ROLL_TIME')
                        if int_value <= int(dice_roll_setting.value):
                            raise forms.ValidationError(
                                f"Dice result time must be greater than dice roll time (currently {dice_roll_setting.value})"
                            )
                    except GameSettings.DoesNotExist:
                        pass
                
                if key == 'ROUND_END_TIME':
                    # ROUND_END_TIME should be greater than DICE_RESULT_TIME
                    try:
                        dice_result_setting = GameSettings.objects.exclude(pk=instance.pk if instance else None).get(key='DICE_RESULT_TIME')
                        if int_value <= int(dice_result_setting.value):
                            raise forms.ValidationError(
                                f"Round end time must be greater than dice result time (currently {dice_result_setting.value})"
                            )
                    except GameSettings.DoesNotExist:
                        pass
                
                return str(int_value)
            except ValueError:
                raise forms.ValidationError(f"{key} must be a valid number")
        
        return value


@admin.register(GameSettings)
class GameSettingsAdmin(admin.ModelAdmin):
    """Admin interface for game configuration settings"""
    form = GameSettingsAdminForm
    list_display = ['key', 'value', 'description', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['key', 'description']
    readonly_fields = ['updated_at']
    
    fieldsets = (
        ('Setting Information', {
            'fields': ('key', 'value', 'description')
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Group timing settings together
        return qs.order_by('key')
    
    def changelist_view(self, request, extra_context=None):
        # Add helpful information about game timing settings
        extra_context = extra_context or {}
        
        # Get current timing values
        from .utils import get_game_setting
        timing_info = {
            'betting_close': get_game_setting('BETTING_CLOSE_TIME', 30),
            'dice_result': get_game_setting('DICE_RESULT_TIME', 51),
            'round_end': get_game_setting('ROUND_END_TIME', 70),
        }
        extra_context['timing_info'] = timing_info
        
        return super().changelist_view(request, extra_context)
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Clear any caches if needed (for future caching implementation)
        if obj.key in ['BETTING_CLOSE_TIME', 'DICE_RESULT_TIME', 'ROUND_END_TIME']:
            # Could invalidate cache here if caching is implemented
            pass


@admin.register(UserSoundSetting)
class UserSoundSettingAdmin(admin.ModelAdmin):
    list_display = ['user', 'background_music_volume', 'is_muted', 'updated_at']
    list_filter = ['is_muted', 'updated_at']
    search_fields = ['user__username']
    readonly_fields = ['updated_at']


@admin.register(MegaSpinProbability)
class MegaSpinProbabilityAdmin(admin.ModelAdmin):
    list_display = ['user', 'prob_1', 'prob_2', 'prob_3', 'prob_4', 'prob_5', 'prob_6', 'prob_7', 'prob_8', 'updated_at']
    search_fields = ['user__username']


@admin.register(DailyRewardProbability)
class DailyRewardProbabilityAdmin(admin.ModelAdmin):
    list_display = ['user', 'prob_low', 'prob_medium', 'prob_high', 'prob_mega', 'updated_at']
    search_fields = ['user__username']









import os

# 1. Fix models.py
with open('models_server_current.py', 'r') as f:
    models_content = f.read()

if 'class MegaSpinProbability' not in models_content:
    models_content += """

class MegaSpinProbability(models.Model):
    \"\"\"Probability configuration for Mega Spin\"\"\"
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mega_spin_probability', null=True, blank=True)
    # If user is null, it's the global default probability
    
    # Probabilities for each slice/number (0-100)
    # Assuming 8 slices for the wheel
    prob_1 = models.FloatField(default=12.5)
    prob_2 = models.FloatField(default=12.5)
    prob_3 = models.FloatField(default=12.5)
    prob_4 = models.FloatField(default=12.5)
    prob_5 = models.FloatField(default=12.5)
    prob_6 = models.FloatField(default=12.5)
    prob_7 = models.FloatField(default=12.5)
    prob_8 = models.FloatField(default=12.5)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Mega Spin Probabilities"

    def __str__(self):
        return f"Mega Spin Prob for {self.user.username if self.user else 'Global Default'}"
"""

with open('models_fixed.py', 'w') as f:
    f.write(models_content)

# 2. Fix serializers.py
with open('serializers_server_current.py', 'r') as f:
    serializers_content = f.read()

if 'class MegaSpinProbabilitySerializer' not in serializers_content:
    serializers_content = serializers_content.replace(
        'from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction, UserSoundSetting',
        'from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction, UserSoundSetting, MegaSpinProbability'
    )
    serializers_content += """

class MegaSpinProbabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MegaSpinProbability
        fields = ['prob_1', 'prob_2', 'prob_3', 'prob_4', 'prob_5', 'prob_6', 'prob_7', 'prob_8', 'updated_at']
        read_only_fields = ['updated_at']

    def validate(self, data):
        # Ensure total probability equals 100
        # Use existing values if not provided in partial update
        p1 = data.get('prob_1', getattr(self.instance, 'prob_1', 12.5) if self.instance else 12.5)
        p2 = data.get('prob_2', getattr(self.instance, 'prob_2', 12.5) if self.instance else 12.5)
        p3 = data.get('prob_3', getattr(self.instance, 'prob_3', 12.5) if self.instance else 12.5)
        p4 = data.get('prob_4', getattr(self.instance, 'prob_4', 12.5) if self.instance else 12.5)
        p5 = data.get('prob_5', getattr(self.instance, 'prob_5', 12.5) if self.instance else 12.5)
        p6 = data.get('prob_6', getattr(self.instance, 'prob_6', 12.5) if self.instance else 12.5)
        p7 = data.get('prob_7', getattr(self.instance, 'prob_7', 12.5) if self.instance else 12.5)
        p8 = data.get('prob_8', getattr(self.instance, 'prob_8', 12.5) if self.instance else 12.5)
        
        total = p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8
        if abs(total - 100.0) > 0.01:
            raise serializers.ValidationError(f"Total probability must equal 100% (currently {total}%)")
        return data
"""

with open('serializers_fixed.py', 'w') as f:
    f.write(serializers_content)

# 3. Fix views.py (This is the most critical one with existing syntax errors)
with open('views_server_current.py', 'r') as f:
    lines = f.readlines()

new_views_lines = []
skip_until = -1
for i, line in enumerate(lines):
    if i <= skip_until:
        continue
    
    # Fix the specific syntax errors we saw in previous logs
    if 'serializer = BetSerializer(bet)' in line and i + 1 < len(lines) and 'return Response({' in lines[i+1]:
        new_views_lines.append('            serializer = BetSerializer(bet)\n')
        new_views_lines.append('            return Response({\n')
        new_views_lines.append("                'bet': serializer.data,\n")
        new_views_lines.append("                'wallet_balance': str(wallet.balance),\n")
        new_views_lines.append("                'round': {\n")
        new_views_lines.append("                    'round_id': round_obj.round_id,\n")
        new_views_lines.append("                    'total_bets': round_obj.total_bets,\n")
        new_views_lines.append("                    'total_amount': str(round_obj.total_amount)\n")
        new_views_lines.append("                }\n")
        new_views_lines.append('            }, status=status.HTTP_201_CREATED)\n')
        # Skip the broken lines (usually 9 lines)
        j = i + 1
        while j < len(lines) and '}, status=status.HTTP_201_CREATED)' not in lines[j]:
            j += 1
        skip_until = j
        continue

    if 'round_obj = GameRound.objects.order_by(\'-start_time\').first()' in line and i > 0 and 'else:' in lines[i-1]:
        new_views_lines.append('            round_obj = GameRound.objects.order_by(\'-start_time\').first()\n')
        continue

    if 'round_data = redis_client.get(\'current_round\')' in line and i > 0 and 'if not current_round_obj:' in lines[i-1]:
        new_views_lines.append('                round_data = redis_client.get(\'current_round\')\n')
        continue

    if 'logger.info("Public last round results API access")' in line and i > 0 and 'try:' in lines[i-1]:
        new_views_lines.append('        logger.info("Public last round results API access")\n')
        continue

    if 'last_round = GameRound.objects.filter(' in line and i > 0 and 'if redis_client:' not in lines[i-1] and 'try:' in lines[i-1]:
        # This is the last_round_results try block
        new_views_lines.append('        last_round = GameRound.objects.filter(\n')
        continue

    new_views_lines.append(line)

# Add Mega Spin View
views_content = "".join(new_views_lines)
if 'def admin_mega_spin_prob' not in views_content:
    views_content = views_content.replace(
        'from .serializers import (',
        'from .serializers import (\n    MegaSpinProbabilitySerializer,'
    )
    views_content = views_content.replace(
        'from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction, UserSoundSetting',
        'from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction, UserSoundSetting, MegaSpinProbability'
    )
    views_content += """

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def admin_mega_spin_prob(request, user_id=None):
    \"\"\"Admin: Get or set Mega Spin probabilities (global or user-specific)\"\"\"
    if user_id:
        user = get_object_or_404(User, id=user_id)
        prob_obj, created = MegaSpinProbability.objects.get_or_create(user=user)
    else:
        prob_obj, created = MegaSpinProbability.objects.get_or_create(user=None)
    
    if request.method == 'GET':
        serializer = MegaSpinProbabilitySerializer(prob_obj)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = MegaSpinProbabilitySerializer(prob_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
"""

with open('views_fixed.py', 'w') as f:
    f.write(views_content)

# 4. Fix urls.py
with open('urls_server_current.py', 'r') as f:
    urls_content = f.read()

if 'admin/mega-spin-prob/' not in urls_content:
    urls_content = urls_content.replace(
        ']',
        "    path('admin/mega-spin-prob/', views.admin_mega_spin_prob, name='admin_mega_spin_prob_global'),\n    path('admin/mega-spin-prob/<int:user_id>/', views.admin_mega_spin_prob, name='admin_mega_spin_prob_user'),\n]"
    )

with open('urls_fixed.py', 'w') as f:
    f.write(urls_content)

# 5. Fix admin.py
with open('admin_server_current.py', 'r') as f:
    admin_content = f.read()

if 'class MegaSpinProbabilityAdmin' not in admin_content:
    admin_content = admin_content.replace(
        'from .models import GameRound, Bet, DiceResult, GameSettings, UserSoundSetting',
        'from .models import GameRound, Bet, DiceResult, GameSettings, UserSoundSetting, MegaSpinProbability'
    )
    admin_content += """

@admin.register(MegaSpinProbability)
class MegaSpinProbabilityAdmin(admin.ModelAdmin):
    list_display = ['user', 'prob_1', 'prob_2', 'prob_3', 'prob_4', 'prob_5', 'prob_6', 'prob_7', 'prob_8', 'updated_at']
    search_fields = ['user__username']
"""

with open('admin_fixed.py', 'w') as f:
    f.write(admin_content)

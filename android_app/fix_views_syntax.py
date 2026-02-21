import os

with open('views_server_latest.py', 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Fix the specific indentation and block errors around line 332
    if 'serializer = BetSerializer(bet)' in line and 'i < len(lines)' and 'return Response({' in lines[i+1]:
        # This is the problematic block
        new_lines.append('            serializer = BetSerializer(bet)\n')
        new_lines.append('            return Response({\n')
        new_lines.append("                'bet': serializer.data,\n")
        new_lines.append("                'wallet_balance': str(wallet.balance),\n")
        new_lines.append("                'round': {\n")
        new_lines.append("                    'round_id': round_obj.round_id,\n")
        new_lines.append("                    'total_bets': round_obj.total_bets,\n")
        new_lines.append("                    'total_amount': str(round_obj.total_amount)\n")
        new_lines.append("                }\n")
        new_lines.append('            }, status=status.HTTP_201_CREATED)\n')
        i += 9 # Skip the broken lines
    elif 'round_obj.total_bets = max(0, round_obj.total_bets - 1)' in line and 'else:' in lines[i-1]:
        # Fix the indentation for the else block in remove_bet
        new_lines.append('                round_obj.total_bets = max(0, round_obj.total_bets - 1)\n')
        i += 1
    else:
        new_lines.append(line)
        i += 1

with open('views_server_fixed.py', 'w') as f:
    f.writelines(new_lines)

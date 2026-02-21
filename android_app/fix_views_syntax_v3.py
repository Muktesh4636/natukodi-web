with open('views_server_debug.py', 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Fix the duplicate closing block
    if '}, status=status.HTTP_201_CREATED)' in line and i + 1 < len(lines) and '}, status=status.HTTP_201_CREATED)' in lines[i+1]:
        new_lines.append(line)
        i += 2
    # Fix the indentation error in remove_bet
    elif 'round_obj = GameRound.objects.order_by(\'-start_time\').first()' in line and 'else:' in lines[i-1]:
        new_lines.append('            round_obj = GameRound.objects.order_by(\'-start_time\').first()\n')
        i += 1
    else:
        new_lines.append(line)
        i += 1

with open('views_server_fixed_v3.py', 'w') as f:
    f.writelines(new_lines)

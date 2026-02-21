with open('views_server_debug.py', 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if '}, status=status.HTTP_201_CREATED)' in line and 'i < len(lines)' and i + 1 < len(lines) and '}, status=status.HTTP_201_CREATED)' in lines[i+1]:
        # Found the duplicate closing block
        new_lines.append(line)
        i += 2 # Skip both the current and the next line (the duplicate)
    else:
        new_lines.append(line)
        i += 1

with open('views_server_fixed_v2.py', 'w') as f:
    f.writelines(new_lines)

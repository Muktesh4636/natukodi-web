with open('admin_views_server_debug.py', 'r') as f:
    lines = f.readlines()

final_lines = []
skip = False
for i in range(len(lines)):
    if skip:
        skip = False
        continue
    line = lines[i]
    if "'page': 'dice-control'," in line and i+1 < len(lines) and '        })' in lines[i+1]:
        final_lines.append(line)
        final_lines.append('        }\n')
        skip = True
    else:
        final_lines.append(line)

with open('admin_views_fixed.py', 'w') as f:
    f.writelines(final_lines)

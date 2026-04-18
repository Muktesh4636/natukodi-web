#!/usr/bin/env python3
"""
Script to update sidebar color from #004D4D to #0f172a
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ADMIN_TEMPLATES_DIR = BASE_DIR / "backend" / "game" / "templates" / "admin"

# All admin template files
ADMIN_FILES = [
    "game_dashboard.html",
    "all_bets.html",
    "deposit_requests.html",
    "players.html",
    "game_settings.html",
    "admin_management.html",
    "wallets.html",
    "user_details.html",
    "transactions.html",
    "round_details.html",
    "recent_rounds.html",
    "edit_admin.html",
    "create_admin.html",
]

def update_sidebar_color(file_path):
    """Update sidebar background color"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Replace #004D4D with #0f172a in sidebar background
        content = re.sub(
            r'(\.sidebar\s*\{[^}]*?background:\s*)#004D4D',
            r'\1#0f172a',
            content,
            flags=re.MULTILINE | re.DOTALL
        )
        
        # Also replace any other occurrences
        content = content.replace('#004D4D', '#0f172a')
        
        if content != original:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated: {file_path.name}")
            return True
        else:
            print(f"⏭️  No changes: {file_path.name}")
            return False
    except Exception as e:
        print(f"❌ Error updating {file_path.name}: {e}")
        return False

def main():
    print("🔄 Updating sidebar color to #0f172a...\n")
    
    updated = 0
    for filename in ADMIN_FILES:
        file_path = ADMIN_TEMPLATES_DIR / filename
        if file_path.exists():
            if update_sidebar_color(file_path):
                updated += 1
        else:
            print(f"⚠️  Not found: {filename}")
    
    print(f"\n✅ Updated {updated} files")

if __name__ == "__main__":
    main()


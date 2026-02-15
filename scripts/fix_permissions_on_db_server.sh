#!/bin/bash

# Script to fix PostgreSQL permissions
# Run this on PostgreSQL server (72.61.255.231) as root

echo "🔐 Fixing PostgreSQL Permissions for muktesh user"
echo "================================================="
echo ""

# Check if postgres user exists
if ! id -u postgres > /dev/null 2>&1; then
    echo "❌ Error: postgres user not found"
    echo "Please install PostgreSQL first"
    exit 1
fi

# Check if dice_game database exists
if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw dice_game; then
    echo "❌ Error: dice_game database not found"
    exit 1
fi

echo "✅ PostgreSQL is installed"
echo "✅ dice_game database exists"
echo ""
echo "Running SQL commands to grant permissions..."
echo ""

# Run SQL commands to grant permissions
sudo -u postgres psql -d dice_game << 'EOF'
-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO muktesh;

-- Grant all privileges on all existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO muktesh;

-- Grant all privileges on all sequences
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO muktesh;

-- Grant execute on all functions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO muktesh;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO muktesh;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO muktesh;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO muktesh;

-- Test permissions
SET ROLE muktesh;
SELECT 'Permissions test:' as status, current_user, current_database();
SELECT 'django_session count:' as test, COUNT(*) FROM django_session;
SELECT 'game_gameround count:' as test, COUNT(*) FROM game_gameround;
RESET ROLE;

\echo ''
\echo '✅ Permissions granted successfully!'
\echo '✅ User muktesh now has full access to all tables'
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SUCCESS! Permissions have been granted."
    echo ""
    echo "Next steps:"
    echo "1. Test from application server (72.61.254.71):"
    echo "   cd /root/Gunduata/backend"
    echo "   source venv/bin/activate"
    echo "   python manage.py shell -c \"from django.contrib.sessions.models import Session; print('Sessions:', Session.objects.count())\""
    echo ""
    echo "2. If test works, restart Django services:"
    echo "   cd /root/Gunduata/backend"
    echo "   bash restart_services.sh"
else
    echo ""
    echo "❌ Error: Failed to grant permissions"
    echo "Please check PostgreSQL logs"
fi

#!/bin/bash

# Script to grant PostgreSQL permissions to muktesh user
# This must be run on the PostgreSQL server (72.61.255.231) as postgres superuser

echo "🔐 Granting PostgreSQL permissions to muktesh user..."
echo "=================================================="
echo ""
echo "⚠️  IMPORTANT: This script must be run on PostgreSQL server (72.61.255.231)"
echo "⚠️  Run as: sudo -u postgres psql -d dice_game"
echo ""
echo "SQL Commands to run:"
echo "===================="
echo ""
cat << 'SQL'
-- Connect to dice_game database
\c dice_game

-- Grant all privileges on all existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO muktesh;

-- Grant all privileges on all sequences (for auto-increment IDs)
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO muktesh;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO muktesh;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO muktesh;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO muktesh;

-- Verify permissions
\dp

-- Test query
SELECT current_user, current_database();
SQL

echo ""
echo "📝 To run these commands:"
echo "   1. SSH to PostgreSQL server: ssh user@72.61.255.231"
echo "   2. Run: sudo -u postgres psql -d dice_game"
echo "   3. Copy and paste the SQL commands above"
echo ""

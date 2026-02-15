-- PostgreSQL Permissions Fix Script
-- Run this on PostgreSQL server (72.61.255.231) as postgres superuser
-- Command: sudo -u postgres psql -d dice_game -f fix_postgres_permissions.sql

-- Connect to dice_game database (if not already connected)
\c dice_game

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO muktesh;

-- Grant all privileges on all existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO muktesh;

-- Grant all privileges on all sequences (for auto-increment IDs)
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO muktesh;

-- Grant execute on all functions (if any)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO muktesh;

-- Set default privileges for future tables created by postgres
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO muktesh;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO muktesh;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO muktesh;

-- Verify permissions on key tables
\dp django_session
\dp django_migrations
\dp game_gameround
\dp accounts_user

-- Test query as muktesh user (this will show if permissions work)
SET ROLE muktesh;
SELECT current_user, current_database();
SELECT COUNT(*) FROM django_session;
SELECT COUNT(*) FROM game_gameround;
RESET ROLE;

-- Show all tables and their permissions
SELECT 
    schemaname,
    tablename,
    tableowner,
    hasindexes,
    hasrules,
    hastriggers
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY tablename;

-- Success message
\echo ''
\echo '✅ Permissions granted successfully!'
\echo '✅ User muktesh now has full access to all tables in dice_game database'
\echo ''

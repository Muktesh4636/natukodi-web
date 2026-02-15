#!/bin/bash

# Fix database permissions on the remote DB server
# Usage: ./scripts/fix_db_permissions.sh

DB_SERVER_IP="72.61.255.231"
DB_SERVER_USER="root"
DB_SERVER_PASS="Gunduata@123"

echo "🔧 Fixing PostgreSQL permissions on $DB_SERVER_IP..."

# Grant ownership of all tables to the postgres user (or ensure it has full rights)
# We'll use psql to run the ownership change commands
SSH_COMMAND="
sudo -u postgres psql -d dice_game -c \"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;\"
sudo -u postgres psql -d dice_game -c \"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;\"
sudo -u postgres psql -d dice_game -c \"ALTER TABLE accounts_user OWNER TO postgres;\"
# Add more tables if needed, or use a loop
for tbl in \$(sudo -u postgres psql -qAt -c \"SELECT tablename FROM pg_tables WHERE schemaname = 'public';\" dice_game); do
    sudo -u postgres psql -d dice_game -c \"ALTER TABLE \$tbl OWNER TO postgres;\"
done
"

sshpass -p "$DB_SERVER_PASS" ssh -o StrictHostKeyChecking=no $DB_SERVER_USER@$DB_SERVER_IP "$SSH_COMMAND"

echo "✅ Permissions fixed on $DB_SERVER_IP"

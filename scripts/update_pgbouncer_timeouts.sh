#!/bin/bash
# Update PgBouncer timeouts on Database Server (72.61.254.74)

cat > /etc/pgbouncer/pgbouncer.ini << 'EOF'
[databases]
dice_game = host=localhost port=5432 dbname=dice_game user=muktesh password=muktesh123

[pgbouncer]
; Pool settings - OPTIMIZED for high concurrency
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 300
min_pool_size = 150
reserve_pool_size = 50
reserve_pool_timeout = 10
max_db_connections = 500
max_user_connections = 2000

; Connection settings
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = any
auth_file = /etc/pgbouncer/userlist.txt

; Logging
logfile = /var/log/pgbouncer/pgbouncer.log
pidfile = /var/run/pgbouncer/pgbouncer.pid
admin_users = postgres
stats_users = postgres

; Performance tuning
server_round_robin = 1
ignore_startup_parameters = extra_float_digits,application_name

; Connection timeout - INCREASED significantly for slow connections
server_connect_timeout = 120
server_login_retry = 120

; Query timeout
query_timeout = 60
query_wait_timeout = 300

; Connection creation rate - allow faster pool growth
server_lifetime = 3600
server_idle_timeout = 600

; Connection pool growth settings
server_reset_query = DISCARD ALL
server_check_delay = 10
server_check_query = SELECT 1
EOF

chown postgres:postgres /etc/pgbouncer/pgbouncer.ini
systemctl restart pgbouncer
sleep 3
systemctl status pgbouncer --no-pager | head -n 5

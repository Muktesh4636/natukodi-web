# Fix PostgreSQL Permissions - Step by Step Instructions

## Problem
The application is getting **Server Error (500)** because the `muktesh` user doesn't have permissions to access PostgreSQL tables.

## Error Message
```
permission denied for table django_session
permission denied for table game_gameround
```

## Solution

### Step 1: SSH to PostgreSQL Server
```bash
ssh user@72.61.255.231
```

### Step 2: Connect to PostgreSQL as Superuser
```bash
sudo -u postgres psql -d dice_game
```

### Step 3: Run the SQL Commands

**Option A: Copy and paste these commands:**

```sql
-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO muktesh;

-- Grant all privileges on all existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO muktesh;

-- Grant all privileges on all sequences (for auto-increment IDs)
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO muktesh;

-- Grant execute on all functions (if any)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO muktesh;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO muktesh;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO muktesh;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO muktesh;
```

**Option B: Use the SQL file (if you can copy it to the server):**
```bash
sudo -u postgres psql -d dice_game -f /path/to/fix_postgres_permissions.sql
```

### Step 4: Verify Permissions
```sql
-- Test as muktesh user
SET ROLE muktesh;
SELECT COUNT(*) FROM django_session;
SELECT COUNT(*) FROM game_gameround;
RESET ROLE;
```

If these queries work without errors, permissions are fixed!

### Step 5: Exit PostgreSQL
```sql
\q
```

### Step 6: Restart Django Application (on application server 72.61.254.71)
```bash
cd /root/Gunduata/backend
bash restart_services.sh
```

## Quick Test After Fixing

On the application server (72.61.254.71), test the connection:
```bash
cd /root/Gunduata/backend
source venv/bin/activate
python manage.py shell -c "from django.contrib.sessions.models import Session; print('Sessions:', Session.objects.count())"
```

If this works without errors, the 500 error should be resolved!

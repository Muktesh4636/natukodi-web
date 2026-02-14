# Load Test Troubleshooting Guide

## Common Login API Errors

### Error: "Method GET not allowed"
**Cause**: HTTP to HTTPS redirect converts POST to GET
**Solution**: Use `--host=https://gunduata.online` (already fixed)

### Error: "Login redirected (status 301)"
**Cause**: URL without trailing slash causes Django redirect
**Solution**: Ensure URL has trailing slash `/api/auth/login/` (already fixed)

### Error: "Failed to login" with status codes
**Possible Causes**:
1. **401 Unauthorized**: Invalid credentials or user doesn't exist
   - Verify test users exist: `docker exec dice_game_web python manage.py shell -c "from accounts.models import User; print(User.objects.filter(username__startswith='testuser_').count())"`
   - Create test users: `docker exec dice_game_web python scripts/create_test_users.py`

2. **429 Too Many Requests**: Rate limiting
   - Reduce spawn rate
   - Increase wait_time between requests

3. **500 Internal Server Error**: Server issue
   - Check server logs: `docker logs dice_game_web --tail 100`
   - Check database connections
   - Check Redis connectivity

4. **504 Gateway Timeout**: Server overloaded
   - Reduce number of concurrent users
   - Check server resources: `docker stats`

## Current Configuration

- **Host**: `https://gunduata.online`
- **Test Users**: 300 users (`testuser_0` to `testuser_299`)
- **Password**: `testpassword123`
- **URL Format**: `/api/auth/login/` (with trailing slash)
- **Redirect Handling**: `allow_redirects=True`

## Response Format

The login API returns:
```json
{
  "user": {...},
  "access": "jwt_access_token",
  "refresh": "jwt_refresh_token"
}
```

## Debugging Steps

1. **Test API directly**:
   ```bash
   curl -X POST https://gunduata.online/api/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser_0","password":"testpassword123"}'
   ```

2. **Check Locust logs**: Look at terminal output for detailed error messages

3. **Check server logs**:
   ```bash
   docker logs dice_game_web --tail 100 | grep -i "login\|error"
   ```

4. **Verify test users exist**:
   ```bash
   docker exec dice_game_web python manage.py shell -c "from accounts.models import User; users = User.objects.filter(username__startswith='testuser_'); print(f'Found {users.count()} test users')"
   ```

5. **Monitor server resources**:
   ```bash
   docker stats dice_game_web
   ```

## If Errors Persist

1. Check the specific error message in Locust UI
2. Check server logs for detailed error information
3. Verify test users exist and have correct passwords
4. Check database connection pool settings
5. Reduce load and gradually increase

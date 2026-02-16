# Exposure API Daily Failure Fix

## Problem Identified

The Exposure API (`/api/game/round/exposure/`) was failing daily due to:

1. **Missing Key Initialization**: Exposure keys were NOT initialized when a new round starts
   - `round:{round_id}:total_exposure`
   - `round:{round_id}:user_exposure` (hash)
   - `round:{round_id}:bet_count`

2. **No TTL on Keys**: Keys were created on-demand without TTL, making them vulnerable to:
   - Redis memory eviction policies
   - Redis restarts
   - Memory pressure cleanup

3. **Poor Fallback Logic**: When Redis keys were missing, the API would fail or return incomplete data

## Root Cause

**Daily Pattern:**
- Round starts → Exposure keys NOT initialized
- First bet placed → Keys created via Lua script (but no TTL)
- Over time → Keys might expire or be evicted
- Next day → Keys missing → API fails

## Fixes Applied

### 1. ✅ Initialize Exposure Keys on Round Start

**File:** `backend/game/management/commands/start_game_timer.py`

**Change:** Added initialization of exposure keys when a new round starts:

```python
# Initialize exposure keys with TTL to prevent daily failures
pipe.set(f"round:{round_obj.round_id}:total_exposure", "0.00", ex=3600)
pipe.set(f"round:{round_obj.round_id}:bet_count", "0", ex=3600)
pipe.hset(f"round:{round_obj.round_id}:user_exposure", mapping={})
pipe.expire(f"round:{round_obj.round_id}:user_exposure", 3600)
```

**Impact:** Keys now exist from round start, preventing "key not found" errors

### 2. ✅ Set TTL in Lua Script

**File:** `backend/game/views.py` - `PLACE_BET_LUA` script

**Change:** Updated Lua script to:
- Check if keys exist before operations
- Set TTL (3600 seconds) when keys are first created
- Accept TTL as parameter

**Impact:** Keys created during betting now have proper expiration

### 3. ✅ Auto-Rebuild Missing Keys

**File:** `backend/game/views.py` - `round_exposure()` function

**Change:** Added logic to:
- Detect when exposure keys are missing
- Rebuild keys from database
- Cache rebuilt keys in Redis with TTL

**Impact:** API can recover from missing keys automatically

## Expected Improvements

| Issue | Before | After |
|-------|--------|-------|
| **Key Initialization** | ❌ Not initialized | ✅ Initialized on round start |
| **TTL on Keys** | ❌ No TTL | ✅ 3600s TTL set |
| **Missing Key Recovery** | ❌ API fails | ✅ Auto-rebuilds from DB |
| **Daily Failures** | ❌ Common | ✅ Should be eliminated |

## Testing

After deployment, verify:

1. **New Round Starts:**
   ```bash
   # Check Redis keys exist
   redis-cli -a Gunduata@123 -h 72.61.254.74
   > GET round:R1771214957:total_exposure
   > GET round:R1771214957:bet_count
   > HGETALL round:R1771214957:user_exposure
   ```

2. **Exposure API Works:**
   ```bash
   curl -H "Authorization: Bearer <token>" \
     https://gunduata.online/api/game/round/exposure/
   ```

3. **Keys Have TTL:**
   ```bash
   redis-cli -a Gunduata@123 -h 72.61.254.74
   > TTL round:R1771214957:total_exposure
   # Should return a number > 0 (seconds remaining)
   ```

## Deployment Steps

1. **Deploy updated code:**
   ```bash
   # On all servers (Server 1, 3, 4)
   cd /root/apk_of_ata/backend
   git pull  # or copy updated files
   docker compose restart web game_timer
   ```

2. **Monitor logs:**
   ```bash
   # Watch for initialization messages
   docker logs -f dice_game_timer | grep "Initialized exposure keys"
   
   # Watch for rebuild messages
   docker logs -f dice_game_web | grep "Rebuilt exposure keys"
   ```

3. **Verify next round:**
   - Wait for next round to start
   - Check Redis keys exist
   - Test exposure API

## Monitoring

Watch for these log messages:

✅ **Success:**
- `"Initialized exposure keys for round {round_id} with 3600s TTL"`
- `"Rebuilt exposure keys for round {round_id} from DB"` (if recovery needed)

⚠️ **Warning:**
- `"Exposure keys missing for round {round_id}, rebuilding from DB..."`

❌ **Error:**
- `"Redis exposure fetch failed: {error}"`
- `"Failed to rebuild exposure keys: {error}"`

## Rollback Plan

If issues occur:

1. Revert `start_game_timer.py` changes
2. Revert `views.py` Lua script changes
3. Restart services

```bash
cd /root/apk_of_ata/backend
git checkout HEAD~1 backend/game/management/commands/start_game_timer.py
git checkout HEAD~1 backend/game/views.py
docker compose restart web game_timer
```

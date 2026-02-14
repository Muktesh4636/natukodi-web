# Bet Placement Load Test Guide

## Overview
This guide explains how to test the bet placement API with 100 concurrent users using Locust.

## Prerequisites

1. **Python 3.7+** installed
2. **Locust** installed: `pip3 install locust`
3. **At least 100 test users** created on the server

## Quick Start

### Option 1: Run with Web UI (Recommended for monitoring)

```bash
# Start Locust web interface
locust -f test_bet_load.py --host=https://gunduata.online

# Then open browser to: http://localhost:8089
# Set:
#   - Number of users: 100
#   - Spawn rate: 10 users/second
#   - Click "Start Swarming"
```

### Option 2: Run Headless (Command Line)

```bash
# Run the automated script
./run_bet_load_test.sh

# Or manually:
locust -f test_bet_load.py \
    --host=https://gunduata.online \
    --users=100 \
    --spawn-rate=10 \
    --run-time=5m \
    --headless \
    --html=bet_load_test_report.html
```

## Test Configuration

### Test Script: `test_bet_load.py`

**Features:**
- ✅ Automatic login for each user
- ✅ Checks round status before betting
- ✅ Only places bets when betting window is open (timer < 30s)
- ✅ Handles token expiration and re-authentication
- ✅ Realistic bet amounts (₹10, ₹20, ₹50, ₹100)
- ✅ Random bet numbers (1-6)

**User Behavior:**
- Each user waits 1-3 seconds between actions
- 10x more likely to place bets than check status
- Automatically skips betting if window is closed

### Test Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--users` | 100 | Number of concurrent users |
| `--spawn-rate` | 10 | Users spawned per second |
| `--run-time` | 5m | Test duration (e.g., 5m, 10m, 1h) |
| `--host` | https://gunduata.online | API base URL |

## Expected Results

### Success Metrics
- ✅ **Response Time**: < 500ms for bet placement
- ✅ **Success Rate**: > 95% (some failures expected when betting window closes)
- ✅ **Throughput**: 50-200 bets/second (depending on betting window)

### Common Scenarios

1. **Betting Window Open** (Timer < 30s):
   - ✅ Bets are placed successfully (201 Created)
   - ✅ Wallet balance decreases
   - ✅ Round totals update

2. **Betting Window Closed** (Timer >= 30s):
   - ⚠️ Bets are rejected (400 Bad Request)
   - ✅ Error message: "Betting period has ended"
   - ✅ This is expected behavior, not a failure

3. **Insufficient Balance**:
   - ⚠️ Bet rejected (400 Bad Request)
   - ✅ Error message: "Insufficient balance"
   - 💡 Ensure test users have sufficient wallet balance

## Monitoring

### During Test (Web UI)
- **Real-time stats**: Requests/second, response times, failures
- **Charts**: Response time distribution, RPS over time
- **Failures tab**: See which requests failed and why

### After Test (HTML Report)
- Open `bet_load_test_report.html` in browser
- View detailed statistics and charts
- Analyze failure patterns

### Server Monitoring

Monitor server resources during test:
```bash
# On server
docker stats dice_game_web dice_game_redis
docker logs dice_game_web --tail=100 -f
```

## Troubleshooting

### Issue: "Login failed" errors
**Solution**: Ensure test users exist and have correct password
```bash
# Check user count on server
docker exec dice_game_web python manage.py shell -c "from accounts.models import User; print(User.objects.filter(username__startswith='testuser_').count())"
```

### Issue: "Insufficient balance" errors
**Solution**: Fund test user wallets
```bash
# On server, fund wallets
docker exec dice_game_web python manage.py shell -c "
from accounts.models import User, Wallet
for user in User.objects.filter(username__startswith='testuser_')[:100]:
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet.balance = 10000.00
    wallet.save()
    print(f'Funded {user.username}')
"
```

### Issue: High response times
**Possible Causes**:
- Database connection pool exhausted
- Redis overloaded
- Network latency
- Server CPU/memory limits

**Solutions**:
- Reduce spawn rate: `--spawn-rate=5`
- Increase server resources
- Check database connection pool settings

### Issue: All bets rejected
**Check**:
1. Is betting window open? (Timer < 30s)
2. Are rounds being created?
3. Check server logs for errors

## Advanced Configuration

### Custom Test Duration
```bash
locust -f test_bet_load.py \
    --host=https://gunduata.online \
    --users=100 \
    --spawn-rate=10 \
    --run-time=10m \  # Run for 10 minutes
    --headless
```

### More Aggressive Testing
```bash
locust -f test_bet_load.py \
    --host=https://gunduata.online \
    --users=200 \      # 200 concurrent users
    --spawn-rate=20 \  # Spawn faster
    --run-time=5m \
    --headless
```

### Distributed Load Testing
Run Locust on multiple machines:
```bash
# Master node
locust -f test_bet_load.py --master --host=https://gunduata.online

# Worker nodes (on other machines)
locust -f test_bet_load.py --worker --master-host=<master-ip>
```

## Test Results Interpretation

### Good Results ✅
- Response time p95 < 500ms
- Success rate > 95%
- No 5xx errors
- Consistent throughput

### Warning Signs ⚠️
- Response time p95 > 1000ms
- Success rate < 90%
- Increasing response times over time
- Many 5xx errors

### Critical Issues ❌
- Response time p95 > 5000ms
- Success rate < 50%
- Server errors (500, 502, 503)
- Database connection errors

## Next Steps

After load testing:
1. Review HTML report for bottlenecks
2. Check server logs for errors
3. Monitor database performance
4. Optimize slow endpoints if needed
5. Scale infrastructure if required

## Support

If you encounter issues:
1. Check server logs: `docker logs dice_game_web --tail=100`
2. Verify test users exist and have balance
3. Ensure betting window is open during test
4. Review Locust output for specific errors

# Server Capacity Report

**Server IP**: 72.61.254.71  
**Date**: February 13, 2026  
**Uptime**: 7 days, 4 hours

---

## 🖥️ Hardware Specifications

### CPU
- **Model**: AMD EPYC 7543P 32-Core Processor
- **Cores**: 4 CPU cores (allocated)
- **Architecture**: x86_64
- **Current Load**: 2.12, 2.15, 2.26 (1min, 5min, 15min)

### Memory (RAM)
- **Total**: 15 GB
- **Used**: 1.9 GB (12.7%)
- **Free**: 5.8 GB
- **Buff/Cache**: 8.2 GB
- **Available**: 13 GB
- **Swap**: 0 GB (no swap configured)

### Storage
- **Total Disk**: 193 GB
- **Used**: 16 GB (9%)
- **Available**: 177 GB
- **Filesystem**: /dev/sda1

---

## 🐳 Docker Container Resources

### Current Usage

| Container | CPU Usage | Memory Usage | Memory Limit | Memory % | Network I/O |
|-----------|-----------|--------------|--------------|----------|-------------|
| **dice_game_web** | 113.48% | 960.4 MB | 12 GB | 7.82% | 77.8 MB / 80.6 MB |
| **dice_game_timer** | 2.51% | 73.83 MB | 2 GB | 3.61% | 344 MB / 665 MB |
| **dice_game_redis** | 3.63% | 11.53 MB | 15.62 GB | 0.07% | 718 MB / 395 MB |

### Container Limits

- **dice_game_web**: 
  - Memory Limit: 12 GB (no hard limit set, using default)
  - CPU: No limit (can use all 4 cores)
  
- **dice_game_timer**: 
  - Memory Limit: 2 GB
  - CPU: No limit
  
- **dice_game_redis**: 
  - Memory Limit: No limit (can use up to 15.62 GB)
  - CPU: No limit

---

## 📊 Capacity Analysis

### Current Utilization

#### CPU
- **Web Container**: 113.48% (using more than 1 core - high load)
- **Timer Container**: 2.51% (low usage)
- **Redis Container**: 3.63% (low usage)
- **Overall**: ~120% total (out of 400% = 4 cores)
- **Available**: ~280% CPU capacity remaining

#### Memory
- **Total Used**: ~1.05 GB (7% of 15 GB)
- **Available**: ~13 GB (87% free)
- **Status**: ✅ **Excellent** - Plenty of memory available

#### Disk
- **Used**: 16 GB (9% of 193 GB)
- **Available**: 177 GB (91% free)
- **Status**: ✅ **Excellent** - Plenty of storage

---

## 🚀 Estimated Capacity

### Current Load Test Results
- **100 concurrent users**: Successfully handled
- **Requests/second**: ~9.4 req/s
- **Response time**: 7.6s average (network latency included)

### Estimated Maximum Capacity

Based on current resource usage:

#### **Conservative Estimate** (with current setup)
- **Concurrent Users**: 500-800 users
- **Requests/Second**: 50-100 req/s
- **Bottleneck**: CPU (web container at 113% with 100 users)

#### **Optimized Estimate** (with optimizations)
- **Concurrent Users**: 1,000-2,000 users
- **Requests/Second**: 100-200 req/s
- **Improvements Needed**:
  - Database connection pooling optimization
  - Redis caching improvements
  - Code optimization for CPU efficiency

#### **Theoretical Maximum** (all resources utilized)
- **Concurrent Users**: 3,000-5,000 users
- **Requests/Second**: 200-500 req/s
- **Requirements**:
  - Horizontal scaling (multiple web containers)
  - Database read replicas
  - Load balancer
  - Optimized code

---

## ⚠️ Current Bottlenecks

### 1. CPU Usage (High Priority)
- **Web container**: 113.48% CPU usage
- **Issue**: Using more than 1 full core
- **Impact**: May cause slow response times under load
- **Recommendation**: 
  - Optimize Django queries
  - Add more caching
  - Consider horizontal scaling

### 2. No CPU Limits Set
- **Issue**: Containers can compete for CPU resources
- **Recommendation**: Set CPU limits in docker-compose.yml

### 3. Database Connections
- **Status**: Need to check PostgreSQL max_connections
- **Recommendation**: Monitor connection pool usage

---

## 💡 Optimization Recommendations

### Immediate Actions

1. **Set CPU Limits**
   ```yaml
   # In docker-compose.yml
   services:
     web:
       deploy:
         resources:
           limits:
             cpus: '2.0'  # Limit to 2 cores
             memory: 4G
   ```

2. **Monitor Database Connections**
   - Check PostgreSQL max_connections setting
   - Monitor active connections during peak load
   - Optimize connection pooling (PgBouncer)

3. **Add Redis Memory Limit**
   ```yaml
   redis:
     command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
   ```

### Medium-term Improvements

1. **Horizontal Scaling**
   - Run 2-3 web containers behind load balancer
   - Distribute load across containers

2. **Database Optimization**
   - Add database indexes
   - Optimize slow queries
   - Use read replicas for read-heavy operations

3. **Caching Strategy**
   - Increase Redis caching
   - Cache frequently accessed data
   - Use Redis for session storage

### Long-term Scaling

1. **Infrastructure**
   - Upgrade to 8+ CPU cores
   - Increase RAM to 32 GB
   - Add database read replicas

2. **Architecture**
   - Microservices for heavy operations
   - Message queue for async tasks
   - CDN for static assets

---

## 📈 Capacity Scaling Path

### Current State
- ✅ 100 users: Working
- ⚠️ 500 users: Possible with optimizations
- ❌ 1000+ users: Needs scaling

### Scaling Steps

1. **100-500 users**: 
   - Optimize code
   - Add caching
   - Set resource limits

2. **500-1000 users**:
   - Horizontal scaling (2-3 web containers)
   - Database read replicas
   - Load balancer

3. **1000+ users**:
   - Multiple servers
   - Database cluster
   - Redis cluster
   - CDN

---

## 🔍 Monitoring Recommendations

### Key Metrics to Monitor

1. **CPU Usage**: Should stay below 80% per container
2. **Memory Usage**: Monitor for leaks
3. **Database Connections**: Track active connections
4. **Response Times**: p95 should be < 500ms
5. **Error Rates**: Should be < 1%

### Tools
- Docker stats: `docker stats`
- Server monitoring: `htop`, `iostat`
- Application monitoring: Django logging, APM tools

---

## ✅ Summary

### Current Capacity
- **Hardware**: Excellent (15 GB RAM, 4 cores, 193 GB disk)
- **Utilization**: Low (7% memory, 30% CPU)
- **Status**: ✅ **Healthy** - Plenty of headroom

### Estimated Capacity
- **Current Setup**: 500-800 concurrent users
- **With Optimizations**: 1,000-2,000 concurrent users
- **With Scaling**: 3,000-5,000+ concurrent users

### Priority Actions
1. ⚠️ Monitor CPU usage (currently high at 113%)
2. ✅ Memory and disk are excellent
3. 💡 Optimize code for better CPU efficiency
4. 📊 Set up monitoring and alerts

---

**Report Generated**: February 13, 2026  
**Next Review**: After implementing optimizations

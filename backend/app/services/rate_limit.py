"""进程内限流 —— 令牌桶，按 (调用方, 桶名) 计数。

存在原因（审计 2026-10 P1-2）：`/api/apikeys/quick` 与 `POST /api/apikeys` 会**真的
向外网发一次验证请求**，而无任何速率限制时可被用来消耗额度。访客又共用同一个
key 池，等于任何能访问端口的人都能触发。

设计取舍：
- **只保护会花钱/出网的端点**，不给普通 GET 加限。前端一页会并发打 6+ 个请求
  （健康检查/会话同步/题库），全局限流会直接把手感打坏。
- 进程内内存计数，不引 Redis——本地单机应用够用，重启即清零也可接受。
  真要多实例部署时换成 Redis 版即可，接口不变。
- 桶按调用方 IP 隔离；反向代理后面会全落到 127.0.0.1，那是全局限而非每人限，
  对「防刷额度」这个目的依然有效（只是粒度变粗）。
"""

from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request


class TokenBucket:
    """单桶令牌桶：capacity 个令牌，每 refill_seconds 补满一次。"""

    __slots__ = ("_capacity", "_refill", "_tokens", "_ts", "_lock")

    def __init__(self, capacity: int, refill_seconds: float):
        self._capacity = capacity
        self._refill = refill_seconds
        self._tokens = float(capacity)
        self._ts = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            # 按时间比例补令牌（比「整桶刷新」平滑，不会一整分钟都拒）
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._ts) / self._refill * self._capacity,
            )
            self._ts = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class RateLimiter:
    """按 key 惰性建桶，附带过期清理防止字典无限增长。"""

    def __init__(self, max_buckets: int = 4096):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._max_buckets = max_buckets

    def hit(self, key: str, capacity: int, refill_seconds: float) -> bool:
        with self._lock:
            if len(self._buckets) >= self._max_buckets:
                # 简单兜底：超量时清掉一半（长时间运行 + 多来源 IP 才会走到）
                for k in list(self._buckets)[: self._max_buckets // 2]:
                    self._buckets.pop(k, None)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(capacity, refill_seconds)
                self._buckets[key] = bucket
        return bucket.allow()


_limiter = RateLimiter()


def client_key(request: Request) -> str:
    """取调用方标识。反向代理后面会统一落到 127.0.0.1（全局限），可接受。"""
    return request.client.host if request.client else "unknown"


def rate_limit(bucket_name: str, capacity: int, refill_seconds: float):
    """生成一个限流依赖。

    capacity / refill_seconds：桶容量与补满耗时。例 capacity=5, refill_seconds=60
    表示平均每分钟 5 次，允许短时突发 5 次。
    """

    async def _dep(request: Request) -> None:
        if not _limiter.hit(f"{bucket_name}:{client_key(request)}", capacity, refill_seconds):
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请稍后再试（限制：每 {refill_seconds:.0f} 秒 {capacity} 次）",
            )

    return _dep

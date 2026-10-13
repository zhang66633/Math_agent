"""SSRF 域名解析 + 限流回归测试（审计 2026-10 P1-1 / P1-2）。

运行: 在 backend/ 目录下 `python -m pytest tests/test_apikeys_hardening.py -q`
"""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.api.apikeys import _is_disallowed_ip, _validate_custom_base_url  # noqa: E402
from app.services.rate_limit import RateLimiter  # noqa: E402

# Depends 在 test_rate_limit_dependency_returns_429 内部导入，避免顶层未使用告警


# ── P1-1 SSRF：域名必须解析后判定 ───────────────────────


def test_http_scheme_still_rejected():
    for url in ("http://api.deepseek.com", "http://example.com/v1"):
        with pytest.raises(HTTPException):
            _validate_custom_base_url(url)


def test_literal_internal_ips_still_rejected():
    for url in (
        "https://127.0.0.1",
        "https://10.0.0.5/v1",
        "https://192.168.1.1",
        "https://169.254.169.254/latest/meta-data",  # 云元数据
        "https://[::1]",
        "https://0.0.0.0",
    ):
        with pytest.raises(HTTPException):
            _validate_custom_base_url(url)


def test_public_literal_ip_accepted():
    assert _validate_custom_base_url("https://1.1.1.1") == "https://1.1.1.1"


def test_proxy_fake_ip_range_is_allowed():
    """198.18.0.0/15 必须放行——本机在代理 fake-ip DNS 后面。

    实测 api.deepseek.com / dashscope.aliyuncs.com / github.com 全部解析到
    198.18.0.x，而 Python 的 ipaddress.is_private 覆盖该段。若按 is_private 拦，
    每个合法服务商地址都会被拒，SSRF 校验等于不可用。
    """
    for ip in ("198.18.0.89", "198.18.0.129", "198.19.255.255"):
        assert not _is_disallowed_ip(ip), f"{ip} 被误拦"
    assert _validate_custom_base_url("https://198.18.0.89") == "https://198.18.0.89"


def test_ipv4_mapped_ipv6_is_judged_by_embedded_ipv4():
    """::ffff:127.0.0.1 之类要按内层 IPv4 判，不能绕过。"""
    assert _is_disallowed_ip("::ffff:127.0.0.1")
    assert _is_disallowed_ip("::ffff:10.0.0.1")
    assert _is_disallowed_ip("::ffff:169.254.169.254")
    assert not _is_disallowed_ip("::ffff:1.1.1.1")


def test_domain_resolving_to_internal_is_rejected(monkeypatch):
    """内网域名 / DNS 指向内网的公网域名都必须被拒——这是本次修复的核心。"""

    def fake_getaddrinfo(host, port, *a, **kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", port, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException) as ei:
        _validate_custom_base_url("https://internal.corp.local")
    assert "内网" in str(ei.value.detail), ei.value.detail


def test_domain_resolving_to_loopback_is_rejected(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException):
        _validate_custom_base_url("https://localhost.example.com")


def test_domain_with_unresolvable_host_is_rejected(monkeypatch):
    """解析失败也拒绝：宁可早失败，也不要等 httpx 连接时才有含糊报错。"""

    def fake_getaddrinfo(host, port, *a, **kw):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException) as ei:
        _validate_custom_base_url("https://no-such-host.invalid")
    assert "无法解析" in str(ei.value.detail)


def test_domain_resolving_to_public_is_accepted(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert _validate_custom_base_url("https://api.deepseek.com/") == "https://api.deepseek.com"


def test_missing_hostname_rejected():
    with pytest.raises(HTTPException):
        _validate_custom_base_url("https://")


# ── P1-2 限流 ─────────────────────────────────────────


def test_bucket_allows_burst_then_throttles():
    rl = RateLimiter(max_buckets=16)
    got = [rl.hit("k", capacity=3, refill_seconds=60) for _ in range(5)]
    assert got == [True, True, True, False, False], got


def test_bucket_refills_over_time():
    """补令牌应按时间比例平滑进行，不是整桶刷新。

    用真实短窗口而非 monkeypatch time.monotonic——后者会打乱全局时钟，
    且建桶时记录的 _ts 与假时钟之间会出现巨大负向跳变，测不出真实行为。
    """
    import time as _time

    rl = RateLimiter(max_buckets=16)
    assert rl.hit("k", capacity=1, refill_seconds=0.1)
    assert not rl.hit("k", capacity=1, refill_seconds=0.1)
    _time.sleep(0.15)
    assert rl.hit("k", capacity=1, refill_seconds=0.1), "过了补充窗口却没恢复令牌"


def test_buckets_are_isolated_per_key():
    rl = RateLimiter(max_buckets=16)
    for _ in range(3):
        assert rl.hit("a", capacity=3, refill_seconds=60)
    assert not rl.hit("a", capacity=3, refill_seconds=60)
    # 另一个 key 不受影响
    assert rl.hit("b", capacity=3, refill_seconds=60)


def test_bucket_map_does_not_grow_unbounded():
    rl = RateLimiter(max_buckets=10)
    for i in range(50):
        rl.hit(f"ip{i}", capacity=1, refill_seconds=60)
    assert len(rl._buckets) <= 10, len(rl._buckets)


def test_rate_limit_dependency_returns_429():
    """走真实 HTTP 验证 429——限流必须真的拦在端点上，而不只是桶逻辑对。"""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.services.rate_limit import rate_limit

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(rate_limit("test_ep", 2, 60))])
    async def _ep():
        return {"ok": True}

    with TestClient(app) as c:
        codes = [c.get("/limited").status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429], codes


if __name__ == "__main__":
    for _fn in [
        test_http_scheme_still_rejected,
        test_literal_internal_ips_still_rejected,
        test_public_literal_ip_accepted,
        test_proxy_fake_ip_range_is_allowed,
        test_ipv4_mapped_ipv6_is_judged_by_embedded_ipv4,
        test_domain_resolving_to_internal_is_rejected,
        test_domain_resolving_to_loopback_is_rejected,
        test_domain_with_unresolvable_host_is_rejected,
        test_domain_resolving_to_public_is_accepted,
        test_missing_hostname_rejected,
        test_bucket_allows_burst_then_throttles,
        test_bucket_refills_over_time,
        test_buckets_are_isolated_per_key,
        test_bucket_map_does_not_grow_unbounded,
        test_rate_limit_dependency_returns_429,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")

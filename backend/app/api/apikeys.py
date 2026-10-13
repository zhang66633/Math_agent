"""API Key 管理 — 存储、验证、CRUD。
外部通过 from .apikeys import get_active_api_key, PROVIDER_PRESETS 使用。"""

import ipaddress
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import GitHubUser, get_current_user, resolve_user_id
from ..config import get_settings
from .schemas.request import ApiKeyCreate, ApiKeyQuickCreate
from .schemas.response import ApiKeyResponse

apikeys_router = APIRouter()

_api_keys_store: dict[
    str, dict
] = {}  # user_id → {key_id: {name, key, provider, model_name, base_url, purpose, masked_key}}
_user_default_keys: dict[str, str] = {}  # user_id → default_key_id
_api_keys_file = None

# 服务商预设：base_url 为 OpenAI 兼容端点（不含路径），anthropic 为原生协议
PROVIDER_PRESETS: dict[str, dict] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "chat_model": "deepseek-v4-flash"},
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode",
        "chat_model": "qwen-plus",
    },
    "glm": {"base_url": "https://open.bigmodel.cn/api/paas", "chat_model": "glm-4-flash"},
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn",
        "chat_model": "deepseek-ai/DeepSeek-V3",
    },
    "openai": {"base_url": "https://api.openai.com", "chat_model": "gpt-4o-mini"},
    "anthropic": {"base_url": "https://api.anthropic.com", "chat_model": "claude-sonnet-4-6"},
}
DEFAULT_EMBEDDING = {"provider": "siliconflow", "model": "BAAI/bge-large-zh-v1.5"}


def _preset_base_url(provider: str, explicit: str = "") -> str:
    """显式 base_url 优先，否则按 provider 预设。"""
    if explicit:
        return explicit.rstrip("/")
    return PROVIDER_PRESETS.get(provider, {}).get("base_url", "")


def _validate_custom_base_url(base_url: str) -> str:
    """校验用户自定义 base_url，防 SSRF（仅 https + 拒绝内网/回环地址）。

    预置服务商地址不经此校验（可信常量表）。
    """
    if not base_url:
        return ""
    u = urlparse(base_url)
    if u.scheme != "https":
        raise HTTPException(status_code=400, detail="自定义 base_url 仅允许 https")
    if not u.hostname:
        raise HTTPException(status_code=400, detail="base_url 缺少主机名")
    try:
        ip = ipaddress.ip_address(u.hostname)
    except ValueError:
        pass  # 域名形式：跳过字面 IP 检查（本地单机应用的务实取舍，已记录于审计计划 004）
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=400, detail="base_url 不允许指向内网地址")
    return base_url.rstrip("/")


def _get_api_keys_path() -> Path:
    global _api_keys_file
    if _api_keys_file is None:
        settings = get_settings()
        _api_keys_file = settings.project_root / "data" / "apikeys.json"
    return _api_keys_file


def _load_api_keys():
    global _api_keys_store, _user_default_keys
    path = _get_api_keys_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _api_keys_store = data.get("keys", {}) or {}
            # 兼容历史格式：default_keys 可能是 list / None / 缺失
            dk = data.get("default_keys")
            if isinstance(dk, dict):
                _user_default_keys = dk
            elif isinstance(dk, list):
                # 旧格式可能是 [key_id1, key_id2] 列表 → 视为空 dict
                _user_default_keys = {}
            else:
                _user_default_keys = {}
            # 兼容旧格式: {key_id: {...}} → 并入 guest 桶
            if _api_keys_store and not any(
                isinstance(v, dict)
                and any(isinstance(vv, dict) and "key" in vv for vv in v.values())
                for v in _api_keys_store.values()
                if isinstance(v, dict)
            ):
                _api_keys_store = {"guest": _api_keys_store}
                if not isinstance(_user_default_keys.get("guest"), str):
                    legacy_default = next(iter(_api_keys_store["guest"].keys()), None)
                    _user_default_keys = {"guest": legacy_default}
            # "legacy" 桶并入 "guest"（旧迁移遗留）
            if "legacy" in _api_keys_store:
                guest = _api_keys_store.setdefault("guest", {})
                for kid, v in _api_keys_store.pop("legacy").items():
                    guest.setdefault(kid, v)
                if "legacy" in _user_default_keys and "guest" not in _user_default_keys:
                    _user_default_keys["guest"] = _user_default_keys.pop("legacy")
        except Exception:
            _api_keys_store = {}
            _user_default_keys = {}


def _save_api_keys():
    path = _get_api_keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "keys": _api_keys_store,
        "default_keys": _user_default_keys,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_user_id(request: Request | None = None, user: GitHubUser | None = None) -> str:
    """Resolve a user ID for API key scoping.

    - Logged-in GitHub user → use login name
    - Guest → use "guest" (shared guest pool)

    逻辑真源在 app.auth.resolve_user_id；此处 guest 桶沿用 "guest" 而非
    "default"，是因为存量 apikeys.json 的钥匙都挂在 "guest" 下，改字面量
    会让已配置的 Key 全部失联。
    """
    return resolve_user_id(user, guest="guest")


def get_active_api_key(user_id: str | None = None, purpose: str = "chat") -> dict | None:
    """获取指定用户指定用途的活跃 API Key（优先默认，其次该用途第一个，chat 可回退任意 key）。"""
    _load_api_keys()
    uid = user_id or "guest"
    user_keys = _api_keys_store.get(uid, {})
    if not user_keys:
        return None
    default_id = _user_default_keys.get(uid)
    if default_id and default_id in user_keys:
        entry = user_keys[default_id]
        if entry.get("purpose", "chat") == purpose:
            return entry
    for entry in user_keys.values():
        if entry.get("purpose", "chat") == purpose:
            return entry
    # chat 用途可回退到任意 key（兼容无 purpose 字段的旧数据）
    if purpose == "chat":
        return next(iter(user_keys.values()))
    return None


@apikeys_router.get("/apikeys/mine")
async def get_my_api_key(user: GitHubUser | None = Depends(get_current_user)):
    """获取当前用户的 API Key 状态（首页快速检查用）。"""
    active = get_active_api_key(_resolve_user_id(user=user))
    if not active:
        return {"has_key": False, "key": None}
    return {
        "has_key": True,
        "key": {
            "masked_key": active.get("masked_key", "****"),
            "provider": active.get("provider", ""),
            "model_name": active.get("model_name", ""),
        },
    }


async def _verify_api_key(
    key: str,
    provider: str,
    model_name: str,
    base_url: str = "",
    purpose: str = "chat",
) -> tuple[bool, str]:
    """验证 API Key 是否有效 — 发送一个最小请求测试连通性。"""
    import httpx

    resolved_url = _preset_base_url(provider, base_url)
    headers = {"Content-Type": "application/json"}

    if provider == "anthropic":
        url = f"{resolved_url or 'https://api.anthropic.com'}/v1/messages"
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
        body = {
            "model": model_name,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }
    elif purpose == "embedding":
        url = f"{resolved_url}/v1/embeddings"
        headers["Authorization"] = f"Bearer {key}"
        body = {"model": model_name, "input": "test"}
    else:
        url = f"{resolved_url}/v1/chat/completions"
        headers["Authorization"] = f"Bearer {key}"
        body = {
            "model": model_name,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code == 200:
                return True, ""
            elif resp.status_code in (401, 403):
                return False, "API Key 无效或被拒绝，请检查 Key 是否正确"
            elif resp.status_code == 404:
                return False, f"接口不存在，请检查服务商与模型名 ({model_name})"
            elif resp.status_code == 429:
                return False, "API 请求过于频繁，请稍后再试"
            else:
                body_text = resp.text[:200]
                return False, f"API 验证失败 (HTTP {resp.status_code}): {body_text}"
    except httpx.ConnectError:
        return False, "无法连接到 API 服务器，请检查网络"
    except Exception as e:
        return False, f"验证请求失败: {str(e)[:100]}"


@apikeys_router.post("/apikeys/quick")
async def quick_add_api_key(
    req: ApiKeyQuickCreate,
    user: GitHubUser | None = Depends(get_current_user),
):
    """快速添加 API Key — 粘贴 Key，按 provider 预设自动补全 + 验证有效性。"""
    _load_api_keys()
    uid = _resolve_user_id(user=user)

    key = req.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="请输入 API Key")

    provider = req.provider or "deepseek"
    if key.startswith("sk-ant") and not req.provider:
        provider = "anthropic"
    if provider not in PROVIDER_PRESETS:
        raise HTTPException(status_code=400, detail=f"不支持的服务商: {provider}")

    preset = PROVIDER_PRESETS[provider]
    model_name = req.model_name or (
        DEFAULT_EMBEDDING["model"] if req.purpose == "embedding" else preset["chat_model"]
    )
    _validate_custom_base_url(req.base_url)
    base_url = _preset_base_url(provider, req.base_url)
    purpose = req.purpose if req.purpose in ("chat", "embedding") else "chat"

    valid, err_msg = await _verify_api_key(key, provider, model_name, base_url, purpose)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Key 验证失败: {err_msg}")

    key_id = str(uuid.uuid4())[:8]
    masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"

    if uid not in _api_keys_store:
        _api_keys_store[uid] = {}

    _api_keys_store[uid][key_id] = {
        "name": req.name or f"{provider} Key ({masked})",
        "key": key,
        "provider": provider,
        "model_name": model_name,
        "base_url": base_url,
        "purpose": purpose,
        "masked_key": masked,
    }

    # chat 用途自动设为该用户默认（embedding key 不占默认位）
    if purpose == "chat":
        _user_default_keys[uid] = key_id

    _save_api_keys()

    return {
        "success": True,
        "id": key_id,
        "masked_key": masked,
        "provider": provider,
        "model_name": model_name,
        "message": "API Key 验证通过，已激活！"
        if purpose == "chat"
        else "向量 Key 验证通过，已可用于知识库索引。",
    }


@apikeys_router.get("/apikeys", response_model=list[ApiKeyResponse])
async def list_api_keys(user: GitHubUser | None = Depends(get_current_user)):
    _load_api_keys()
    uid = _resolve_user_id(user=user)
    user_keys = _api_keys_store.get(uid, {})
    default_id = _user_default_keys.get(uid)
    return [
        ApiKeyResponse(
            id=kid,
            name=v.get("name", ""),
            provider=v.get("provider", "deepseek"),
            model_name=v.get("model_name", ""),
            masked_key=v.get("masked_key", "****"),
            is_default=kid == default_id,
            base_url=v.get("base_url", ""),
            purpose=v.get("purpose", "chat"),
        )
        for kid, v in user_keys.items()
    ]


@apikeys_router.post("/apikeys", response_model=ApiKeyResponse)
async def create_api_key(req: ApiKeyCreate, user: GitHubUser | None = Depends(get_current_user)):
    _load_api_keys()
    uid = _resolve_user_id(user=user)

    purpose = req.purpose if req.purpose in ("chat", "embedding") else "chat"
    _validate_custom_base_url(req.base_url)
    base_url = _preset_base_url(req.provider, req.base_url)

    valid, err_msg = await _verify_api_key(req.key, req.provider, req.model_name, base_url, purpose)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Key 验证失败: {err_msg}")

    key_id = str(uuid.uuid4())[:8]
    masked = req.key[:4] + "****" + req.key[-4:] if len(req.key) > 8 else "****"

    if uid not in _api_keys_store:
        _api_keys_store[uid] = {}

    _api_keys_store[uid][key_id] = {
        "name": req.name,
        "key": req.key,
        "provider": req.provider,
        "model_name": req.model_name,
        "base_url": base_url,
        "purpose": purpose,
        "masked_key": masked,
    }

    if purpose == "chat" and not _user_default_keys.get(uid):
        _user_default_keys[uid] = key_id

    _save_api_keys()

    return ApiKeyResponse(
        id=key_id,
        name=req.name,
        provider=req.provider,
        model_name=req.model_name,
        masked_key=masked,
        is_default=key_id == _user_default_keys.get(uid),
        base_url=base_url,
        purpose=purpose,
    )


@apikeys_router.delete("/apikeys/{key_id}")
async def delete_api_key(key_id: str, user: GitHubUser | None = Depends(get_current_user)):
    _load_api_keys()
    uid = _resolve_user_id(user=user)
    user_keys = _api_keys_store.get(uid, {})
    if key_id not in user_keys:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    del _api_keys_store[uid][key_id]
    if _user_default_keys.get(uid) == key_id:
        _user_default_keys[uid] = (
            next(iter(_api_keys_store[uid].keys()), None) if _api_keys_store[uid] else None
        )
    _save_api_keys()
    return {"success": True, "message": "API Key 已删除"}


@apikeys_router.post("/apikeys/{key_id}/default")
async def set_default_api_key(key_id: str, user: GitHubUser | None = Depends(get_current_user)):
    _load_api_keys()
    uid = _resolve_user_id(user=user)
    user_keys = _api_keys_store.get(uid, {})
    if key_id not in user_keys:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    _user_default_keys[uid] = key_id
    _save_api_keys()
    return {"success": True, "message": "已设为默认"}

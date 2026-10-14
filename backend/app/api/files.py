"""文件上传/下载 + 图片服务。"""

import re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import get_settings

files_router = APIRouter()

# 路径参数只允许字母、数字、点、下划线、短横线；拒绝 "." / ".." 及纯点号段（防路径穿越）
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_path_segment(value: str, label: str) -> str:
    """校验路径片段合法性，防止路径穿越。"""
    stripped = value.strip()
    if not _SAFE_NAME_RE.match(stripped) or set(stripped) <= {"."}:
        raise HTTPException(status_code=400, detail=f"非法{label}: {value}")
    return value


# ── File upload / download ───────────────────────────────────────


def _get_uploads_dir() -> Path:
    settings = get_settings()
    uploads = settings.project_root / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


# 上传限制
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".txt",
    ".pdf",
    ".json",
    ".py",
    ".mat",
    ".dat",
    ".tsv",
    ".md",
    ".docx",
    ".doc",
    # 2026-10-14 补：项目自带的 2023C 竞赛数据就是 parquet（87.8 万行销售明细），
    # 沙箱内 pandas+pyarrow 可直接 read_parquet。不加这一条，用户只能先把
    # parquet 转 CSV 才能上传——而大文件转 CSV 很容易超 20MB 上限。
    ".parquet",
}


@files_router.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件到 data/uploads/ 目录（限 20MB，白名单扩展名）。"""
    # 扩展名校验
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '{suffix}'，允许: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    uploads_dir = _get_uploads_dir()
    file_id = str(uuid.uuid4())[:8]
    stored_name = f"{file_id}{suffix}"
    stored_path = uploads_dir / stored_name

    try:
        # 流式写入 + 大小检查
        size = 0
        with stored_path.open("wb") as f:
            while chunk := file.file.read(1024 * 1024):  # 1MB chunks
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    f.close()
                    stored_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="文件超过 20MB 限制")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "stored_name": stored_name,
        "size": stored_path.stat().st_size,
        "url": f"/api/files/{file_id}",
    }


@files_router.get("/files/{file_id}")
async def download_file(file_id: str):
    """下载已上传的文件。"""
    _validate_path_segment(file_id, "file_id")
    uploads_dir = _get_uploads_dir()
    # Find the file with this id regardless of extension
    matches = list(uploads_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在")
    stored_path = matches[0]
    return FileResponse(
        str(stored_path), media_type="application/octet-stream", filename=stored_path.name
    )


# ── Image serving ─────────────────────────────────────────────────


@files_router.get("/images/{run_id}/{filename}")
async def get_image(run_id: str, filename: str):
    """获取求解 Agent 生成的图表（png/jpg/gif 等，按扩展名给 media type）。

    temp 目录被系统清理时，回退读持久化副本 data/chat_images/{run_id}。
    """
    _validate_path_segment(run_id, "run_id")
    _validate_path_segment(filename, "filename")
    img_dir = (Path(tempfile.gettempdir()) / "mathmodel_outputs" / run_id).resolve()
    img_path = (img_dir / filename).resolve()
    # 二次确认：resolve 后必须仍在 img_dir 内（is_relative_to 语义严格，防前缀误判）
    if not img_path.is_relative_to(img_dir):
        raise HTTPException(status_code=400, detail="非法路径")
    if not img_path.exists():
        # temp 已清理 → 回退持久化副本（chat 模式图片落盘 data/chat_images/{run_id}）
        persist_dir = (
            get_settings().project_root / "data" / "chat_images" / run_id
        ).resolve()
        persist_path = (persist_dir / filename).resolve()
        if persist_path.is_relative_to(persist_dir) and persist_path.exists():
            img_path = persist_path
        else:
            raise HTTPException(status_code=404, detail="图片不存在")
    _media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    media_type = _media_types.get(img_path.suffix.lower(), "image/png")
    return FileResponse(str(img_path), media_type=media_type)


@files_router.get("/task_files/{task_id}/{filename}")
async def get_task_file(task_id: str, filename: str):
    """获取任务文件区中持久化保存的文件（生成的图表/结果等）。"""
    _validate_path_segment(task_id, "task_id")
    _validate_path_segment(filename, "filename")
    settings = get_settings()
    file_dir = (settings.project_root / "data" / "task_files" / task_id).resolve()
    file_path = (file_dir / filename).resolve()
    if not file_path.is_relative_to(file_dir):
        raise HTTPException(status_code=400, detail="非法路径")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = "image/png" if file_path.suffix.lower() == ".png" else "application/octet-stream"
    return FileResponse(str(file_path), media_type=media_type, filename=filename)

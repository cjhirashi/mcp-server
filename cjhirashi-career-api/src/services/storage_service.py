"""
Storage Service - MinIO (S3-compatible) object storage for uploaded files.
Implements Single Responsibility Principle (bucket I/O only, no DB access).
"""
import json
import logging
import re
import uuid
from datetime import timedelta
from typing import BinaryIO, Optional

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from config import settings

logger = logging.getLogger(__name__)

_client: Optional[Minio] = None


# ============================================================================
# Bucket
# ============================================================================

def get_client() -> Minio:
    """Lazily create the MinIO client - internal Docker network traffic, no TLS needed
    (the public HTTPS endpoint is terminated by Caddy in cjhirashi-srv, not here)."""
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=False,
        )
    return _client


def ensure_bucket() -> None:
    """Create the bucket if missing and make only its `public/` prefix
    anonymously readable - called once at app startup. Everything under
    `private/` has no anonymous access at all; reading a private object
    always requires a short-lived presigned URL (see get_presigned_url),
    generated only after this service's own JWT-scoped ownership check."""
    client = get_client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
        logger.info("Created MinIO bucket '%s'", settings.MINIO_BUCKET)

    public_read_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{settings.MINIO_BUCKET}/public/*"],
            }
        ],
    }
    client.set_bucket_policy(settings.MINIO_BUCKET, json.dumps(public_read_policy))


# ============================================================================
# Subida de archivos
# ============================================================================

def slugify_category(category: str) -> str:
    """Turn a free-typed category into a safe S3 key prefix (folder) - lowercase,
    alphanumerics/hyphens only, no leading/trailing/duplicate hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", category.strip().lower()).strip("-")
    return slug


def _build_key(
    original_filename: str, category: Optional[str], is_public: bool, name_hint: Optional[str] = None
) -> str:
    """`public/<categoria>/<uuid>.ext` or `private/<categoria>/<uuid>.ext` - the
    leading segment is what the bucket policy above keys off of, so an object's
    visibility is a real property of *where it lives*, not just a DB flag.
    `name_hint` (already a slug) prefixes the unique name instead of a bare
    uuid, for objects that want a human-readable filename (e.g. agent
    Visual-generated images) - still uuid-suffixed to avoid collisions."""
    extension = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if name_hint:
        stem = f"{name_hint}-{uuid.uuid4().hex[:8]}"
    else:
        stem = uuid.uuid4().hex
    unique_name = f"{stem}.{extension}" if extension else stem
    slug = slugify_category(category) if category else ""
    visibility = "public" if is_public else "private"
    parts = [visibility] + ([slug] if slug else []) + [unique_name]
    return "/".join(parts)


def upload_file(
    data: BinaryIO,
    original_filename: str,
    size: int,
    content_type: str,
    category: Optional[str] = None,
    is_public: bool = True,
    name_hint: Optional[str] = None,
) -> str:
    """Upload a file, returning the unique object key it was stored under
    (never the original filename, to avoid collisions/overwrites)."""
    stored_filename = _build_key(original_filename, category, is_public, name_hint)
    get_client().put_object(
        settings.MINIO_BUCKET,
        stored_filename,
        data,
        length=size,
        content_type=content_type or "application/octet-stream",
    )
    return stored_filename


def set_visibility(stored_filename: str, category: Optional[str], is_public: bool) -> str:
    """Move an object between the `public/` and `private/` prefixes (server-side
    copy + delete of the original - MinIO has no in-place "rename"). Returns the
    new key. No-op-safe: if the object is already in the requested prefix, the
    caller should skip calling this rather than copy an object onto itself."""
    client = get_client()
    extension = stored_filename.rsplit(".", 1)[-1] if "." in stored_filename else ""
    new_key = _build_key(f"x.{extension}" if extension else "x", category, is_public)
    client.copy_object(settings.MINIO_BUCKET, new_key, CopySource(settings.MINIO_BUCKET, stored_filename))
    client.remove_object(settings.MINIO_BUCKET, stored_filename)
    return new_key


def check_connection() -> bool:
    """Authenticate against MinIO with the configured credentials and confirm the
    bucket exists - used by GET /system/readiness. False on any S3Error (bad
    credentials, bucket missing, MinIO unreachable), never raises."""
    try:
        return get_client().bucket_exists(settings.MINIO_BUCKET)
    except S3Error:
        return False


def delete_file(stored_filename: str) -> bool:
    """Delete an object. Returns False (instead of raising) if it was already gone,
    since the caller's DB row is the source of truth for whether it 'exists'."""
    try:
        get_client().remove_object(settings.MINIO_BUCKET, stored_filename)
        return True
    except S3Error as e:
        if e.code == "NoSuchKey":
            return False
        raise


# ============================================================================
# URLs prefirmadas
# ============================================================================

def get_public_url(stored_filename: str) -> str:
    return f"{settings.MINIO_PUBLIC_URL}/{settings.MINIO_BUCKET}/{stored_filename}"


def get_presigned_url(stored_filename: str, expires_seconds: int = 300) -> str:
    """Short-lived signed URL for a `private/` object - the only way to read one,
    since the bucket policy grants anonymous access to `public/` alone."""
    return get_client().presigned_get_object(
        settings.MINIO_BUCKET, stored_filename, expires=timedelta(seconds=expires_seconds)
    )


def get_object_stream(stored_filename: str):
    """Raw urllib3 HTTPResponse for an object, for the API to re-stream as a
    forced download (Content-Disposition: attachment). Caller must call
    `.close()` and `.release_conn()` when done - FastAPI's StreamingResponse
    does this automatically when passed the response's `.stream()` generator
    plus a background task, see routes/files.py."""
    return get_client().get_object(settings.MINIO_BUCKET, stored_filename)

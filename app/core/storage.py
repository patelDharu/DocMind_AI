# app/core/storage.py
"""
DocMind AI — Pluggable Storage Layer
Provides seamless abstraction for:
1. S3-compatible 3rd-party object storage (AWS S3, MinIO, Cloudflare R2, Wasabi, Supabase).
2. Local filesystem storage (development & fallback mode).
"""

import os
import io
import mimetypes
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, Union, BinaryIO

logger = logging.getLogger("docmind.storage")

DEFAULT_LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"


class BaseStorageBackend(ABC):
    """Abstract base storage backend interface."""

    backend_name: str = "base"

    @abstractmethod
    def upload_file(
        self,
        file_data: Union[str, Path, bytes, BinaryIO],
        filename: str,
        content_type: Optional[str] = None,
        user_email: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store a document file.
        Returns metadata dict containing storage_key, filename, size_bytes, url, backend.
        """
        pass

    @abstractmethod
    def download_file(
        self,
        storage_key: str,
        local_path: Optional[Path] = None,
    ) -> Path:
        """
        Ensure file is downloaded / available locally at local_path.
        Returns Path to the local file.
        """
        pass

    @abstractmethod
    def read_bytes(self, storage_key: str) -> bytes:
        """Read and return full file content as bytes."""
        pass

    @abstractmethod
    def delete_file(self, storage_key: str) -> bool:
        """Delete a single file by storage key."""
        pass

    @abstractmethod
    def delete_document_files(
        self,
        document_id: str,
        user_email: Optional[str] = None,
    ) -> int:
        """Delete all stored artifacts related to a document_id. Returns deleted count."""
        pass

    @abstractmethod
    def get_url(self, storage_key: str, expires_in: int = 3600) -> str:
        """Return a public, presigned, or API URL to access the file."""
        pass

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check whether the file exists in storage."""
        pass


class S3StorageBackend(BaseStorageBackend):
    """
    Production-grade S3 Storage Backend.
    Supports AWS S3, MinIO, Cloudflare R2, Supabase S3, Wasabi, and LocalStack.
    """

    backend_name = "s3"

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        prefix: Optional[str] = None,
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise ImportError(
                "boto3 is required for S3StorageBackend. Run `pip install boto3`."
            ) from e

        self.bucket_name = (
            bucket_name
            or os.getenv("S3_BUCKET_NAME")
            or os.getenv("AWS_S3_BUCKET")
            or os.getenv("STORAGE_BUCKET")
        )
        if not self.bucket_name:
            raise ValueError(
                "S3_BUCKET_NAME environment variable is required to use S3 storage."
            )

        self.prefix = (
            prefix
            if prefix is not None
            else os.getenv("S3_PREFIX", "documents/")
        ).strip("/")
        if self.prefix:
            self.prefix += "/"

        access_key = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region_name = (
            region_name
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")

        client_kwargs: Dict[str, Any] = {
            "service_name": "s3",
            "region_name": self.region_name,
            "config": Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        }

        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key.strip("'\"")
            client_kwargs["aws_secret_access_key"] = secret_key.strip("'\"")

        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url.strip("'\"")

        self.s3_client = boto3.client(**client_kwargs)
        self.cache_dir = DEFAULT_LOCAL_DIR / "_s3_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Initialized S3StorageBackend: bucket='{self.bucket_name}', "
            f"region='{self.region_name}', endpoint='{self.endpoint_url or 'aws-default'}'"
        )

    def _build_key(self, filename: str, user_email: Optional[str] = None, document_id: Optional[str] = None) -> str:
        safe_filename = Path(filename).name
        parts = [self.prefix] if self.prefix else []
        if user_email:
            sanitized_email = "".join(c if c.isalnum() or c in ".-_@" else "_" for c in user_email.lower())
            parts.append(f"{sanitized_email}/")
        if document_id and not safe_filename.startswith(f"{document_id}_"):
            safe_filename = f"{document_id}_{safe_filename}"
        parts.append(safe_filename)
        return "".join(parts)

    def upload_file(
        self,
        file_data: Union[str, Path, bytes, BinaryIO],
        filename: str,
        content_type: Optional[str] = None,
        user_email: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = self._build_key(filename, user_email=user_email, document_id=document_id)

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        extra_args = {"ContentType": content_type}

        if isinstance(file_data, (str, Path)):
            path = Path(file_data)
            size_bytes = path.stat().st_size
            with open(path, "rb") as f:
                self.s3_client.upload_fileobj(f, self.bucket_name, key, ExtraArgs=extra_args)
        elif isinstance(file_data, bytes):
            size_bytes = len(file_data)
            buffer = io.BytesIO(file_data)
            self.s3_client.upload_fileobj(buffer, self.bucket_name, key, ExtraArgs=extra_args)
        else:
            # File-like object
            stream = file_data
            if hasattr(stream, "seek"):
                stream.seek(0, os.SEEK_END)
                size_bytes = stream.tell()
                stream.seek(0)
            else:
                size_bytes = 0
            self.s3_client.upload_fileobj(stream, self.bucket_name, key, ExtraArgs=extra_args)

        presigned_url = self.get_url(key)
        logger.info(f"Uploaded file to S3: s3://{self.bucket_name}/{key} ({size_bytes} bytes)")
        return {
            "storage_key": key,
            "filename": Path(key).name,
            "size_bytes": size_bytes,
            "url": presigned_url,
            "backend": self.backend_name,
            "bucket": self.bucket_name,
        }

    def download_file(
        self,
        storage_key: str,
        local_path: Optional[Path] = None,
    ) -> Path:
        dest_path = local_path or (self.cache_dir / Path(storage_key).name)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading s3://{self.bucket_name}/{storage_key} -> {dest_path}")
        self.s3_client.download_file(self.bucket_name, storage_key, str(dest_path))
        return dest_path

    def read_bytes(self, storage_key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=storage_key)
        return response["Body"].read()

    def delete_file(self, storage_key: str) -> bool:
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            # Also clean cache file if present
            cache_file = self.cache_dir / Path(storage_key).name
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except Exception:
                    pass
            logger.info(f"Deleted S3 object: s3://{self.bucket_name}/{storage_key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting S3 object s3://{self.bucket_name}/{storage_key}: {e}")
            return False

    def delete_document_files(
        self,
        document_id: str,
        user_email: Optional[str] = None,
    ) -> int:
        """Delete all objects matching document_id in S3."""
        deleted_count = 0
        try:
            # Look up with prefix
            search_prefix = self.prefix
            if user_email:
                sanitized_email = "".join(c if c.isalnum() or c in ".-_@" else "_" for c in user_email.lower())
                search_prefix = f"{self.prefix}{sanitized_email}/"

            paginator = self.s3_client.get_paginator("list_objects_v2")
            objects_to_delete = []

            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=search_prefix):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    filename = Path(key).name
                    if filename.startswith(f"{document_id}_"):
                        objects_to_delete.append({"Key": key})

            if objects_to_delete:
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": objects_to_delete},
                )
                deleted_count = len(objects_to_delete)
                logger.info(f"Deleted {deleted_count} S3 objects matching document_id '{document_id}'")

            # Clean cache directory as well
            for cached in self.cache_dir.glob(f"{document_id}_*"):
                try:
                    cached.unlink()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error deleting document files for '{document_id}' in S3: {e}")

        return deleted_count

    def get_url(self, storage_key: str, expires_in: int = 3600) -> str:
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": storage_key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.warning(f"Failed to generate presigned S3 URL for {storage_key}: {e}")
            return f"s3://{self.bucket_name}/{storage_key}"

    def exists(self, storage_key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False


class LocalStorageBackend(BaseStorageBackend):
    """
    Local filesystem storage backend.
    Default for local development, tests, and environments without S3 credentials.
    """

    backend_name = "local"

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or DEFAULT_LOCAL_DIR
        self.root_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized LocalStorageBackend at '{self.root_dir}'")

    def _resolve_path(self, storage_key: str) -> Path:
        safe_key = Path(storage_key).name
        return self.root_dir / safe_key

    def upload_file(
        self,
        file_data: Union[str, Path, bytes, BinaryIO],
        filename: str,
        content_type: Optional[str] = None,
        user_email: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_filename = Path(filename).name
        if document_id and not safe_filename.startswith(f"{document_id}_"):
            stored_filename = f"{document_id}_{safe_filename}"
        else:
            stored_filename = safe_filename

        dest_path = self.root_dir / stored_filename
        if isinstance(file_data, (str, Path)):
            src = Path(file_data)
            if src.resolve() != dest_path.resolve():
                with open(src, "rb") as rf, open(dest_path, "wb") as wf:
                    for chunk in iter(lambda: rf.read(65536), b""):
                        wf.write(chunk)
            size_bytes = dest_path.stat().st_size
        elif isinstance(file_data, bytes):
            size_bytes = len(file_data)
            with open(dest_path, "wb") as f:
                f.write(file_data)
        else:
            size_bytes = 0
            with open(dest_path, "wb") as f:
                if hasattr(file_data, "seek"):
                    file_data.seek(0)
                for chunk in iter(lambda: file_data.read(65536), b""):
                    f.write(chunk)
                    size_bytes += len(chunk)

        return {
            "storage_key": stored_filename,
            "filename": stored_filename,
            "size_bytes": size_bytes,
            "url": str(dest_path),
            "backend": self.backend_name,
            "path": str(dest_path),
        }

    def download_file(
        self,
        storage_key: str,
        local_path: Optional[Path] = None,
    ) -> Path:
        src = self._resolve_path(storage_key)
        if local_path and local_path.resolve() != src.resolve():
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(src, "rb") as rf, open(local_path, "wb") as wf:
                for chunk in iter(lambda: rf.read(65536), b""):
                    wf.write(chunk)
            return local_path
        return src

    def read_bytes(self, storage_key: str) -> bytes:
        path = self._resolve_path(storage_key)
        with open(path, "rb") as f:
            return f.read()

    def delete_file(self, storage_key: str) -> bool:
        path = self._resolve_path(storage_key)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception as e:
                logger.error(f"Failed to delete local file {path}: {e}")
                return False
        return False

    def delete_document_files(
        self,
        document_id: str,
        user_email: Optional[str] = None,
    ) -> int:
        deleted = 0
        for p in self.root_dir.glob(f"{document_id}_*"):
            try:
                p.unlink()
                deleted += 1
            except Exception:
                pass
        return deleted

    def get_url(self, storage_key: str, expires_in: int = 3600) -> str:
        path = self._resolve_path(storage_key)
        return str(path)

    def exists(self, storage_key: str) -> bool:
        return self._resolve_path(storage_key).exists()


_storage_instance: Optional[BaseStorageBackend] = None


def is_s3_configured() -> bool:
    """Returns True if S3 bucket configuration is provided in environment variables."""
    backend_env = (os.getenv("STORAGE_BACKEND") or "").strip().lower()
    bucket = os.getenv("S3_BUCKET_NAME") or os.getenv("AWS_S3_BUCKET") or os.getenv("STORAGE_BUCKET")
    if backend_env == "s3":
        return True
    return bool(bucket)


def get_storage(force_reinit: bool = False) -> BaseStorageBackend:
    """Singleton getter for the configured storage backend."""
    global _storage_instance
    if _storage_instance is not None and not force_reinit:
        return _storage_instance

    if is_s3_configured():
        try:
            _storage_instance = S3StorageBackend()
            logger.info("Storage initialized with S3StorageBackend.")
            return _storage_instance
        except Exception as e:
            logger.warning(
                f"Failed to initialize S3StorageBackend ({e}). Falling back to LocalStorageBackend."
            )

    _storage_instance = LocalStorageBackend()
    return _storage_instance

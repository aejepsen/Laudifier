import os
import re
import uuid
import boto3
from botocore.config import Config
from pathlib import Path

_USE_LOCAL  = os.getenv("USE_LOCAL_STORAGE", "true").lower() == "true"
_LOCAL_PATH = Path(os.getenv("LOCAL_STORAGE_PATH", "./storage"))


class StorageService:
    def __init__(self):
        if _USE_LOCAL:
            (_LOCAL_PATH / "laudos").mkdir(parents=True, exist_ok=True)
            (_LOCAL_PATH / "exports").mkdir(exist_ok=True)
            self._s3 = None
        else:
            self._s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                region_name=os.getenv("S3_REGION", "auto"),
                config=Config(signature_version="s3v4"),
            )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Remove path separators e caracteres perigosos — previne path traversal."""
        safe = re.sub(r"[^\w\-_\.]", "_", Path(filename).name)
        return safe[:100] or "upload"

    def upload_document(self, content: bytes, filename: str, user_id: str) -> str:
        safe_name = self._sanitize_filename(filename)
        key = f"{user_id}/{uuid.uuid4().hex}/{safe_name}"
        if _USE_LOCAL:
            path = _LOCAL_PATH / "laudos" / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return str(path)
        bucket = os.getenv("S3_BUCKET_LAUDOS", "laudifier-laudos")
        self._s3.put_object(Bucket=bucket, Key=key, Body=content)
        return f"{os.getenv('S3_ENDPOINT_URL')}/{bucket}/{key}"

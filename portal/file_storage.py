"""S3 access for the customer file-sharing feature.

Mirrors media_signing.py's SigV4 client, but for uploading/downloading
customer-shared files. The bucket is private (Block-Public-Access); objects
are only reachable via short-lived presigned URLs. Keys are always built under
a per-company prefix so a customer can never read or write outside their org.

For now this targets the same bucket as doc images, namespaced under
settings.FILESHARE_KEY_PREFIX (default "fileshare/"). Point FILESHARE_BUCKET at
a dedicated private bucket later without changing this module.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def _s3():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1'),
            endpoint_url=getattr(settings, 'AWS_S3_ENDPOINT_URL', None) or None,
            # Force SigV4 — not the deprecated SigV2 the default client emits here.
            config=Config(signature_version='s3v4'),
        )
    return _client


def build_key(company_id, bucket_id, file_id, original_name):
    """Per-company, per-bucket, per-file key. Filename kept for nice downloads."""
    safe = (original_name or 'file').replace('/', '_').replace('\\', '_')
    return (
        f"{settings.FILESHARE_KEY_PREFIX}/companies/{company_id}"
        f"/{bucket_id}/{file_id}/{safe}"
    )


def presign_put(key, content_type):
    return _s3().generate_presigned_url(
        'put_object',
        Params={
            'Bucket': settings.FILESHARE_BUCKET,
            'Key': key,
            'ContentType': content_type or 'application/octet-stream',
        },
        ExpiresIn=settings.FILESHARE_PRESIGN_TTL,
    )


def presign_get(key, download_name=None):
    params = {'Bucket': settings.FILESHARE_BUCKET, 'Key': key}
    if download_name:
        params['ResponseContentDisposition'] = f'attachment; filename="{download_name}"'
    return _s3().generate_presigned_url(
        'get_object', Params=params, ExpiresIn=settings.FILESHARE_PRESIGN_TTL
    )


def presign_view(key, mime=None):
    """Presigned GET that renders inline (for PDF/image preview in an iframe)
    rather than forcing a download."""
    params = {'Bucket': settings.FILESHARE_BUCKET, 'Key': key, 'ResponseContentDisposition': 'inline'}
    if mime:
        params['ResponseContentType'] = mime
    return _s3().generate_presigned_url(
        'get_object', Params=params, ExpiresIn=settings.FILESHARE_PRESIGN_TTL
    )


# Magic-byte signatures for the types we ever render inline. Used to reject a
# file whose real content doesn't match its extension (e.g. HTML uploaded as
# .pdf) — the cheap, no-infra complement to a full AV scanner.
SIGNATURES = {
    'pdf': [b'%PDF'],
    'png': [b'\x89PNG\r\n\x1a\n'],
    'gif': [b'GIF87a', b'GIF89a'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
    'webp': [b'RIFF'],
}


def head_bytes(key, n=16):
    """Read the first n bytes of an object via a ranged GET (cheap)."""
    try:
        r = _s3().get_object(
            Bucket=settings.FILESHARE_BUCKET, Key=key, Range=f'bytes=0-{n - 1}',
        )
        return r['Body'].read(n)
    except Exception as e:
        logger.warning("head_bytes(%s): %s", key, e)
        return b''


def signature_ok(key, original_name):
    """True unless the file's real magic bytes contradict its extension (only
    enforced for types we have a signature for — pdf/images)."""
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    sigs = SIGNATURES.get(ext)
    if not sigs:
        return True  # no signature on file for this type — nothing to check
    head = head_bytes(key, 16)
    if not head:
        return True  # couldn't read — don't block on a transient S3 error
    return any(head.startswith(s) for s in sigs)


def head_size(key):
    """Return object size in bytes, or None if the object isn't there."""
    try:
        r = _s3().head_object(Bucket=settings.FILESHARE_BUCKET, Key=key)
        return r.get('ContentLength')
    except Exception as e:
        logger.warning("head_size(%s): %s", key, e)
        return None


def delete_object(key):
    try:
        _s3().delete_object(Bucket=settings.FILESHARE_BUCKET, Key=key)
        return True
    except Exception as e:
        logger.warning("delete_object(%s): %s", key, e)
        return False

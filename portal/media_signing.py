"""
Render-time S3 presigned URL signing for doc images.

The citemed-docku bucket is private (Block-Public-Access on), so image
objects can't be fetched via plain S3 URLs. The sync stores *plain* (unsigned)
bucket URLs in rendered_html; this module rewrites them to short-lived
presigned URLs at request time.

Why render-time instead of baking signed URLs into the stored HTML:
  - No expiry time bomb — every URL is freshly signed (1 hour) per request.
  - Survives credential rotation — when the AWS keys change, the next render
    signs with the new keys; no re-sync of stored content needed.
  - Uses SigV4 (1h << the 7-day cap), so we don't depend on deprecated SigV2.
"""
import re
import urllib.parse

from django.conf import settings

# Fresh URLs each request; 1 hour is plenty for a page view.
_PRESIGN_TTL = 3600

_client = None
_url_pattern = None


def _bucket_prefix():
    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '') or ''
    if not bucket:
        return None
    return f'https://{bucket}.s3.amazonaws.com/'


def _s3_client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1'),
            # Force SigV4 — not the deprecated SigV2 the default client emits here.
            config=Config(signature_version='s3v4'),
        )
    return _client


def sign_media_urls(html):
    """
    Replace plain citemed-docku S3 URLs in `html` with fresh presigned URLs.
    No-op when S3 isn't configured or the HTML has no bucket URLs.
    """
    if not html:
        return html
    prefix = _bucket_prefix()
    if not prefix or prefix not in html:
        return html

    global _url_pattern
    if _url_pattern is None:
        # Match the bucket URL + key, stopping at a quote, whitespace, or '<'.
        _url_pattern = re.compile(re.escape(prefix) + r'([^\s"\'<>)]+)')

    bucket = settings.AWS_STORAGE_BUCKET_NAME
    client = _s3_client()

    def _replace(m):
        # The baked key may be URL-encoded (spaces as %20 etc.); presigning
        # needs the raw key.
        key = urllib.parse.unquote(m.group(1))
        try:
            return client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=_PRESIGN_TTL,
            )
        except Exception:
            # On any signing error, leave the original URL untouched rather
            # than corrupt the page.
            return m.group(0)

    return _url_pattern.sub(_replace, html)

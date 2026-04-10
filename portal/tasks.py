from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_confluence_incremental():
    from django.conf import settings
    from portal.confluence.sync import sync_space
    try:
        result = sync_space(settings.CONFLUENCE_SPACE_KEY, full=False)
        logger.info(f"Incremental sync: {result}")
        return result
    except Exception as e:
        logger.error(f"Incremental sync failed: {e}", exc_info=True)
        raise


@shared_task
def sync_confluence_full():
    from django.conf import settings
    from portal.confluence.sync import sync_space
    try:
        result = sync_space(settings.CONFLUENCE_SPACE_KEY, full=True)
        logger.info(f"Full sync: {result}")
        return result
    except Exception as e:
        logger.error(f"Full sync failed: {e}", exc_info=True)
        raise


@shared_task
def sync_page(confluence_id):
    from portal.confluence.client import ConfluenceClient
    from portal.confluence.sync import sync_space
    from portal.models import DocPage
    try:
        page = DocPage.objects.get(confluence_id=confluence_id)
        client = ConfluenceClient()
        full_page = client.get_page_body(confluence_id)
        from portal.confluence.sync import sync_space
        # Re-run a targeted single-page sync by forcing update
        page.confluence_version = 0
        page.save(update_fields=['confluence_version'])
        from django.conf import settings
        sync_space(settings.CONFLUENCE_SPACE_KEY, full=False)
    except Exception as e:
        logger.error(f"sync_page {confluence_id} failed: {e}", exc_info=True)
        raise

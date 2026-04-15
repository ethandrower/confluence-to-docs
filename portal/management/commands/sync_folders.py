"""
Create Confluence folder entries in the database and fix parent relationships.

Confluence uses 'folder' type nodes to organize pages, but our sync pipeline
only imports 'page' type items. This command creates placeholder DocPage
entries for folders so the tree structure is correct.

Usage:
    python manage.py sync_folders

This is idempotent — safe to run multiple times.
"""
import re

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from portal.models import DocPage


# Folder definitions discovered via Confluence MCP API.
# Format: (confluence_id, title, parent_confluence_id, space_key, position)
FOLDERS = [
    # V5.5.4 folders under "V5.5.4 - current version" (371032142)
    ('689405958', 'V5.5.4 Literature Module', '371032142', 'ECD', 0),
    ('688488452', 'V5.5.4 CiteSource Module', '371032142', 'ECD', 1),
    # Sub-folders under V5.5.4 Literature Module
    ('689471489', 'V5.5.4 Protocol Setup', '689405958', 'ECD', 0),
    ('688848898', 'V5.5.4 Running Searches and Uploading Results', '689405958', 'ECD', 1),
    ('689176579', 'V5.5.4 Abstract Review', '689405958', 'ECD', 2),
    ('689274883', 'V5.5.4 Full Text Review & Data Extraction', '689405958', 'ECD', 3),
    ('688128003', 'V5.5.4 Report Generation', '689405958', 'ECD', 4),
]

# Parent overrides: (child_confluence_id → correct_parent_confluence_id)
# These pages exist in the DB but have wrong/null parents because their
# folder parents weren't synced. Maps from MCP tree discovery.
PARENT_FIXES = {
    # Under V5.5.4 Literature Module (689405958)
    '371032196': '689405958',  # v5.5.4 Quickstart
    '371033092': '689405958',  # v5.5.4 Adverse Event Review
    # Under V5.5.4 Protocol Setup (689471489)
    '371032275': '689471489',  # v5.5.4 Defining Your Search Protocol
    '371032340': '689471489',  # v5.5.4 How to Set Search Terms
    '371032396': '689471489',  # Define Exclusion Reasons
    '371032429': '689471489',  # Defining Extraction Fields
    '371032462': '689471489',  # Generate Search Protocol
    # Under V5.5.4 Running Searches (688848898)
    '371032513': '688848898',  # v5.5.4 Upload Search Results
    '371032570': '688848898',  # v5.5.4 Removing Duplicates
    # Under V5.5.4 Abstract Review (689176579)
    '371032616': '689176579',  # v5.5.4 Keyword Highlighting
    '371032659': '689176579',  # v5.5.4 Abstract Screening
    '371032678': '689176579',  # v5.5.4 The 1st Pass Abstract Review Screen
    # Under V5.5.4 Full Text Review (689274883)
    '371032758': '689274883',  # v5.5.4 Uploading and Storing Full Text Articles
    '371032786': '689274883',  # v5.5.4 Appraisal States and Statuses
    '371032805': '689274883',  # v5.5.4 2nd Pass Extractions Page
    '371032841': '689274883',  # v5.5.4 Filling out Extraction Fields and Forms
    # Under V5.5.4 CiteSource Module (688488452)
    '371033259': '688488452',  # v5.5.4 Cite While You Write Add-In
    '371033177': '688488452',  # v5.5.4 Manage All Citations Page
    # v5.5.4 Report Generation and Downloads → under Literature Module folder
    '371032869': '689405958',  # v5.5.4 Report Generation and Downloads (has children)
}


class Command(BaseCommand):
    help = 'Create folder entries and fix parent relationships for Confluence folders'

    def handle(self, *args, **options):
        created = 0
        skipped = 0

        # Step 1: Create folder entries
        for cid, title, parent_cid, space_key, position in FOLDERS:
            if DocPage.objects.filter(confluence_id=cid).exists():
                skipped += 1
                continue

            base_slug = slugify(title)[:200] or f'folder-{cid}'
            slug = base_slug
            counter = 1
            while DocPage.objects.filter(slug=slug).exists():
                counter += 1
                slug = f'{base_slug}-{counter}'

            DocPage.objects.create(
                confluence_id=cid,
                title=title,
                slug=slug,
                rendered_html='',
                raw_storage='',
                space_key=space_key,
                is_published=True,
                is_folder=True,
                position=position,
            )
            created += 1
            self.stdout.write(f'  Created folder: {title}')

        self.stdout.write(f'Folders: {created} created, {skipped} already existed')

        # Step 2: Set parent relationships for folders
        folder_linked = 0
        for cid, _, parent_cid, _, _ in FOLDERS:
            try:
                folder = DocPage.objects.get(confluence_id=cid)
                parent = DocPage.objects.get(confluence_id=parent_cid)
                if folder.parent_id != parent.id:
                    folder.parent = parent
                    folder.save(update_fields=['parent'])
                    folder_linked += 1
            except DocPage.DoesNotExist:
                self.stderr.write(f'  Warning: could not link folder {cid} → {parent_cid}')

        self.stdout.write(f'Folder parents linked: {folder_linked}')

        # Step 3: Fix page parent relationships
        fixed = 0
        for child_cid, parent_cid in PARENT_FIXES.items():
            try:
                child = DocPage.objects.get(confluence_id=child_cid)
                parent = DocPage.objects.get(confluence_id=parent_cid)
                if child.parent_id != parent.id:
                    child.parent = parent
                    child.save(update_fields=['parent'])
                    fixed += 1
                    self.stdout.write(f'  Fixed: {child.title} → {parent.title}')
            except DocPage.DoesNotExist:
                self.stderr.write(f'  Warning: could not fix {child_cid} → {parent_cid}')

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} folders created, {folder_linked} folder parents linked, {fixed} page parents fixed'
        ))

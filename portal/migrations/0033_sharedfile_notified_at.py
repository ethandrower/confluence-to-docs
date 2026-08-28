from django.db import migrations, models


def mark_existing_notified(apps, schema_editor):
    """Treat every file that already exists as already reported.

    Without this the column lands NULL on the entire back catalogue and the
    first send_upload_digests run emails staff about every file ever uploaded.
    Those uploads either were notified at the time or were missed months ago;
    either way nobody wants the replay.

    uploaded_at, not now(): the value should read as "this was current news
    back then", and it keeps any future query that buckets by notified_at from
    seeing one enormous spike on deploy day.
    """
    SharedFile = apps.get_model('portal', 'SharedFile')
    SharedFile.objects.filter(notified_at__isnull=True).update(
        notified_at=models.F('uploaded_at'))


def unmark(apps, schema_editor):
    # Reversing only needs to restore the column's pre-backfill state; the
    # AddField below drops it anyway.
    SharedFile = apps.get_model('portal', 'SharedFile')
    SharedFile.objects.update(notified_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0032_sharedfile_upload_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='sharedfile',
            name='notified_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(mark_existing_notified, unmark),
    ]

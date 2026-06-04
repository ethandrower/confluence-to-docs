from django.db import migrations

# Grant admin to the initial team and remove the ops mailbox (TG-672 setup).
# Only updates rows that already exist — safe to run on any environment.
ADMIN_EMAILS = [
    'abaron@citemed.com',      # Alicia Baron-Barlow
    'dzanica1@gmail.com',      # Dzana
    'edrower@citemed.com',     # Ethan Drower
    'hpatel@fuzionx.com',      # Het Patel
    'pmurphy@citemed.com',     # Priscilla Murphy
    'vklimkowski@fuzionx.com', # V. Klimkowski
]
REMOVE_EMAILS = ['ops@citemedical.com']


def apply(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    PortalUser.objects.filter(email__in=REMOVE_EMAILS).delete()
    for email in ADMIN_EMAILS:
        PortalUser.objects.filter(email__iexact=email).update(role='admin', access_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0005_seed_admin_users'),
    ]

    operations = [
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]

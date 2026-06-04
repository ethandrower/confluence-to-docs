from django.db import migrations

# Promote the platform owners to the top tier (protected from regular admins).
OWNER_EMAILS = [
    'hpatel@fuzionx.com',     # Het Patel
    'edrower@citemed.com',    # Ethan Drower
    'pmurphy@citemed.com',    # Priscilla Murphy
]


def apply(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    for email in OWNER_EMAILS:
        PortalUser.objects.filter(email__iexact=email).update(role='owner', access_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0006_grant_admins'),
    ]

    operations = [
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]

from django.db import migrations

# Seed the initial admins so they retain access once the allowlist gate is on.
# Priscilla is added by an admin through the new admin portal on first login.
ADMIN_EMAILS = [
    'hpatel@fuzionx.com',
    'edrower@citemed.com',
]


def seed_admins(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    for email in ADMIN_EMAILS:
        PortalUser.objects.update_or_create(
            email=email,
            defaults={'role': 'admin', 'access_enabled': True},
        )


def unseed_admins(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    PortalUser.objects.filter(email__in=ADMIN_EMAILS).update(role='customer')


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0004_company_portaluser_access_enabled_portaluser_role_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_admins, unseed_admins),
    ]

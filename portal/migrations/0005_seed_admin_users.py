from django.db import migrations

# Seed the initial admins so they retain access once the allowlist gate is on.
# Priscilla is added by an admin through the new admin portal on first login.
ADMINS = [
    ('hpatel@fuzionx.com', 'Het Patel'),
    ('edrower@citemed.com', 'Ethan Drower'),
]


def seed_admins(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    for email, name in ADMINS:
        PortalUser.objects.update_or_create(
            email=email,
            defaults={'role': 'admin', 'access_enabled': True, 'name': name},
        )


def unseed_admins(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    PortalUser.objects.filter(email__in=[e for e, _ in ADMINS]).update(role='customer')


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0004_company_portaluser_access_enabled_portaluser_role_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_admins, unseed_admins),
    ]

"""Seed a demo/sandbox customer account so staff can open the customer-facing
portal in a second browser (via auth.demo_login, no magic link). Idempotent."""
from django.db import migrations


DEMO_EMAIL = 'demo@citemed.com'
DEMO_COMPANY = 'Demo Company (Sandbox)'


def seed(apps, schema_editor):
    Company = apps.get_model('portal', 'Company')
    PortalUser = apps.get_model('portal', 'PortalUser')

    company, _ = Company.objects.get_or_create(name=DEMO_COMPANY)
    user, _ = PortalUser.objects.get_or_create(
        email=DEMO_EMAIL,
        defaults={'name': 'Demo Customer', 'role': 'customer'},
    )
    user.role = 'customer'
    user.company = company
    user.access_enabled = True
    user.is_demo = True
    user.save()


def unseed(apps, schema_editor):
    PortalUser = apps.get_model('portal', 'PortalUser')
    Company = apps.get_model('portal', 'Company')
    PortalUser.objects.filter(email=DEMO_EMAIL).delete()
    Company.objects.filter(name=DEMO_COMPANY).delete()


class Migration(migrations.Migration):
    dependencies = [('portal', '0012_fileshare_is_demo')]
    operations = [migrations.RunPython(seed, unseed)]

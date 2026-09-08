"""Open, inspect and act on a customer's initial user request (REV-45).

The operator path, the same way `magic_link` is the operator path for signing
in as somebody. The HTTP admin API does all of this too, but a CS person
setting up a customer is usually already in a terminal running the other
activation steps, and a command that prints the roster is faster than clicking
through a UI to read six rows.

    python manage.py user_request --list
    python manage.py user_request --open "Acme Devices" --note "..."
    python manage.py user_request --show 3
    python manage.py user_request --provision 3
    python manage.py user_request --invite 3

`--provision` and `--invite` are separate flags for the same reason they are
separate endpoints: provisioning must never email. See portal/roster_provision.py.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portal import roster_provision
from portal.models import Company, RequestedUser, UserRequest


class Command(BaseCommand):
    help = 'Open and manage initial user request forms.'

    def add_arguments(self, parser):
        parser.add_argument('--list', action='store_true',
                            help='Every request, newest first.')
        parser.add_argument('--open', metavar='COMPANY',
                            help='Open a request for this company (by name).')
        parser.add_argument('--note', default='',
                            help='Message shown to the customer above the form.')
        parser.add_argument('--show', type=int, metavar='ID',
                            help='Print one request and its roster.')
        parser.add_argument('--provision', type=int, metavar='ID',
                            help='Create portal accounts. Sends nothing.')
        parser.add_argument('--invite', type=int, metavar='ID',
                            help='Email sign-in links to provisioned people.')

    def handle(self, *args, **opts):
        if opts['list']:
            return self._list()
        if opts['open']:
            return self._open(opts['open'], opts['note'])
        if opts['show']:
            return self._show(opts['show'])
        if opts['provision']:
            return self._provision(opts['provision'])
        if opts['invite']:
            return self._invite(opts['invite'])
        self.stdout.write(self.help)
        self.stdout.write('Run with --help for the options.')

    def _get(self, request_id):
        req = UserRequest.objects.filter(pk=request_id).first()
        if req is None:
            raise CommandError(f'No user request with id {request_id}.')
        return req

    def _list(self):
        rows = UserRequest.objects.select_related('company').prefetch_related('users')
        if not rows:
            self.stdout.write('No user requests yet.')
            return
        for req in rows:
            users = list(req.users.all())
            added = sum(1 for u in users if u.added_at)
            invited = sum(1 for u in users if u.activation_email_sent_at)
            self.stdout.write(
                f'{req.pk:>4}  {req.company.name[:32]:<32}  {req.status:<10}  '
                f'{len(users)} listed / {added} set up / {invited} invited')

    def _open(self, company_name, note):
        # Exact first, then a substring match — company names carry brackets and
        # suffixes ("Northwind Medical (QA)") that are tedious to type exactly
        # and awkward to quote through ssh. Ambiguity is refused rather than
        # guessed: opening a request against the wrong customer would put
        # another company's name in front of them.
        company = Company.objects.filter(name__iexact=company_name).first()
        if company is None:
            matches = list(Company.objects.filter(name__icontains=company_name)[:5])
            if len(matches) == 1:
                company = matches[0]
            elif len(matches) > 1:
                raise CommandError(
                    f'{company_name!r} matches several companies: '
                    f'{", ".join(c.name for c in matches)}. Be more specific.')
        if company is None:
            raise CommandError(
                f'No company named {company_name!r}. '
                f'Known: {", ".join(Company.objects.values_list("name", flat=True)[:20])}')

        existing = UserRequest.objects.filter(
            company=company,
            status__in=(UserRequest.STATUS_DRAFT, UserRequest.STATUS_SENT,
                        UserRequest.STATUS_SUBMITTED)).first()
        if existing:
            raise CommandError(
                f'{company.name} already has an open request (#{existing.pk}). '
                f'Two live forms for one customer means two rosters.')

        req = UserRequest.objects.create(
            company=company, note=note,
            status=UserRequest.STATUS_SENT, sent_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(
            f'Opened user request #{req.pk} for {company.name}.'))
        self.stdout.write(
            f'  Anyone at {company.name} with portal access now sees '
            f'"Set up your team" at /users.')

    def _show(self, request_id):
        req = self._get(request_id)
        self.stdout.write(
            f'#{req.pk}  {req.company.name}  [{req.status}]')
        if req.note:
            self.stdout.write(f'  note: {req.note}')
        self.stdout.write(
            f'  modules offered: {", ".join(req.licensed_modules())}')
        users = list(req.users.all())
        if not users:
            self.stdout.write('  (nobody on the roster yet)')
            return
        for u in users:
            status = ('invited' if u.activation_email_sent_at
                      else 'set up' if u.added_at else 'pending')
            self.stdout.write(
                f'  {u.email:<38} {u.role_type:<10} {status:<8} '
                f'{", ".join(u.module_labels())}')

    def _provision(self, request_id):
        req = self._get(request_id)
        result = roster_provision.provision(req)
        self.stdout.write(self.style.SUCCESS(
            f"Provisioned: {result['created']} created, {result['updated']} "
            f"updated, {result['skipped']} skipped."))
        for problem in result['problems']:
            self.stdout.write(self.style.WARNING(
                f"  {problem['email']}: {problem['message']}"))
        self.stdout.write(
            '  Nothing was emailed. Use --invite when you are ready to tell them.')

    def _invite(self, request_id):
        req = self._get(request_id)
        result = roster_provision.send_invites(req)
        self.stdout.write(self.style.SUCCESS(
            f"Sent {result['sent']} invite(s)."))
        for problem in result['problems']:
            self.stdout.write(self.style.WARNING(
                f"  {problem['email']}: {problem['message']}"))

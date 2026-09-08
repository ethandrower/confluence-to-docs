"""The initial user request form (REV-45).

Three things are being asserted here that are easy to get wrong and expensive to
get wrong in production.

The first is that the two status columns cannot be typed. "Activation Email
Sent?" and "Added?" are the customer's own spreadsheet headings, so a sheet
carrying them WILL be uploaded, and a form field bound to them WOULD be posted.
Both must be inert on the way in and truthful on the way out, or the roster
becomes a place where somebody records that an email went out that never did.

The second is that provisioning does not email. REV-26's first rule, and the
only version of it that means anything is a test that reads the mailbox.

The third is tenancy. A roster is a list of a customer's colleagues and their
access levels; a cross-company read here is a real disclosure.
"""
import csv
import io
import json

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from portal import roster
from portal.models import (
    Company, PortalUser, RequestedUser, RosterImport, UserRequest,
)


# ── Parsing: pure functions, no database ─────────────────────────────────────

class SniffMappingTests(TestCase):
    def test_reads_the_template_we_hand_out(self):
        mapping = roster.sniff_mapping(roster.TEMPLATE_HEADERS)
        self.assertEqual(mapping['0'], roster.FIELD_FIRST_NAME)
        self.assertEqual(mapping['1'], roster.FIELD_LAST_NAME)
        self.assertEqual(mapping['2'], roster.FIELD_EMAIL)
        self.assertEqual(mapping['3'], roster.FIELD_MODULES)
        self.assertEqual(mapping['4'], roster.FIELD_ROLE)
        self.assertEqual(mapping['7'], roster.FIELD_NOTE)

    def test_our_own_status_columns_are_recognised_then_ignored(self):
        # A sheet that came from our template HAS these columns. Calling a
        # heading we told them to use "unrecognised" would be our bug, and
        # importing it would let a customer declare their own invites sent.
        mapping = roster.sniff_mapping(roster.TEMPLATE_HEADERS)
        self.assertEqual(mapping['5'], roster.FIELD_IGNORED_STATUS)
        self.assertEqual(mapping['6'], roster.FIELD_IGNORED_STATUS)
        self.assertEqual(roster.unmapped_headers(roster.TEMPLATE_HEADERS, mapping), [])

    def test_tolerates_the_spellings_people_actually_send(self):
        mapping = roster.sniff_mapping(
            ['E-Mail Address', 'Given Name', 'Surname', 'Permissions', 'Products'])
        self.assertEqual(mapping['0'], roster.FIELD_EMAIL)
        self.assertEqual(mapping['1'], roster.FIELD_FIRST_NAME)
        self.assertEqual(mapping['2'], roster.FIELD_LAST_NAME)
        self.assertEqual(mapping['3'], roster.FIELD_ROLE)
        self.assertEqual(mapping['4'], roster.FIELD_MODULES)

    def test_a_specific_header_is_not_overwritten_by_a_vaguer_later_one(self):
        mapping = roster.sniff_mapping(['First Name', 'Name'])
        self.assertEqual(mapping['0'], roster.FIELD_FIRST_NAME)
        self.assertEqual(mapping.get('1'), roster.FIELD_FULL_NAME)

    def test_reports_columns_it_does_not_understand(self):
        headers = ['Email', 'Cost Centre']
        mapping = roster.sniff_mapping(headers)
        self.assertEqual(roster.unmapped_headers(headers, mapping), ['Cost Centre'])


class NormaliseTests(TestCase):
    def test_role_survives_the_stray_space_in_our_own_template(self):
        # The template literally says "Fulfiller/ Edit".
        for text in ('Fulfiller/ Edit', 'Fulfiller / Edit', 'fulfiller-edit',
                     'Editor', 'writer'):
            self.assertEqual(roster.normalise_role(text),
                             RequestedUser.ROLE_FULFILLER, text)

    def test_role_is_none_when_meaningless_rather_than_defaulted_quietly(self):
        # Filing an unreadable role as Viewer would hand somebody the wrong
        # access with no warning anywhere.
        self.assertIsNone(roster.normalise_role('Wizard'))
        self.assertIsNone(roster.normalise_role(''))

    def test_modules_split_on_the_separators_spreadsheets_produce(self):
        keys, unknown = roster.normalise_modules('Literature, CiteSource')
        self.assertEqual(keys, ['literature', 'citesource'])
        self.assertEqual(unknown, [])
        keys, _ = roster.normalise_modules('Ready View; Vigilance')
        self.assertEqual(keys, ['readyview', 'vigilance'])
        keys, _ = roster.normalise_modules('Pathways and Literature')
        self.assertEqual(keys, ['literature', 'pathways'])

    def test_module_order_is_canonical_not_typed(self):
        # So two rows listing the same access compare equal.
        a, _ = roster.normalise_modules('Vigilance, Literature')
        b, _ = roster.normalise_modules('Literature, Vigilance')
        self.assertEqual(a, b)

    def test_unknown_module_is_returned_in_the_customers_own_words(self):
        keys, unknown = roster.normalise_modules('Literature, Telepathy')
        self.assertEqual(keys, ['literature'])
        self.assertEqual(unknown, ['Telepathy'])

    def test_a_module_they_are_not_licensed_for_is_refused(self):
        keys, unknown = roster.normalise_modules(
            'Literature, Pathways', allowed=['literature'])
        self.assertEqual(keys, ['literature'])
        self.assertEqual(unknown, ['Pathways'])

    def test_full_name_falls_back_to_last_word_as_surname(self):
        self.assertEqual(roster.split_full_name('Anna Lee'), ('Anna', 'Lee'))
        self.assertEqual(roster.split_full_name('Maria del Carmen Ruiz'),
                         ('Maria del Carmen', 'Ruiz'))
        self.assertEqual(roster.split_full_name('Cher'), ('Cher', ''))
        self.assertEqual(roster.split_full_name(''), ('', ''))


class ParseFileTests(TestCase):
    def test_reads_excels_utf8_csv_with_its_byte_order_mark(self):
        # Excel's "CSV UTF-8" writes a BOM; without utf-8-sig it rides along on
        # the first header and the email column stops matching.
        content = '﻿Email,Role Type\na@x.com,Admin\n'.encode('utf-8')
        headers, rows = roster.parse_file('roster.csv', content)
        self.assertEqual(headers[0], 'Email')
        self.assertEqual(rows, [['a@x.com', 'Admin']])

    def test_reads_semicolon_separated_csv(self):
        content = b'Email;Role Type\na@x.com;Viewer\n'
        headers, rows = roster.parse_file('roster.csv', content)
        self.assertEqual(headers, ['Email', 'Role Type'])
        self.assertEqual(rows, [['a@x.com', 'Viewer']])

    def test_blank_lines_are_dropped(self):
        content = b'Email\n\na@x.com\n\n'
        _, rows = roster.parse_file('roster.csv', content)
        self.assertEqual(rows, [['a@x.com']])

    def test_empty_file_is_an_error_not_an_empty_roster(self):
        with self.assertRaises(roster.RosterParseError):
            roster.parse_file('roster.csv', b'')

    def test_legacy_xls_is_refused_with_advice(self):
        with self.assertRaises(roster.RosterParseError) as ctx:
            roster.parse_file('roster.xls', b'\xd0\xcf\x11\xe0')
        self.assertIn('.xlsx', str(ctx.exception))

    def test_reads_a_real_xlsx(self):
        # Excel is what most customers will actually send, so the .xlsx path
        # needs a real workbook rather than a mocked reader.
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(['First Name', 'Email', 'Modules'])
        ws.append(['Anna', 'anna@x.com', 'Literature'])
        buf = io.BytesIO()
        wb.save(buf)

        headers, rows = roster.parse_file('roster.xlsx', buf.getvalue())
        self.assertEqual(headers, ['First Name', 'Email', 'Modules'])
        self.assertEqual(rows, [['Anna', 'anna@x.com', 'Literature']])

    def test_xlsx_ragged_rows_are_padded_not_misaligned(self):
        # A trailing empty cell is dropped by openpyxl, which would shift every
        # value left of it into the wrong column.
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(['First Name', 'Email', 'Notes'])
        ws.append(['Anna', 'anna@x.com'])
        buf = io.BytesIO()
        wb.save(buf)

        headers, rows = roster.parse_file('roster.xlsx', buf.getvalue())
        self.assertEqual(len(rows[0]), len(headers))
        preview = roster.build_preview(headers, rows, roster.sniff_mapping(headers))
        self.assertEqual(preview[0]['email'], 'anna@x.com')


class BuildPreviewTests(TestCase):
    def setUp(self):
        self.headers = roster.TEMPLATE_HEADERS
        self.mapping = roster.sniff_mapping(self.headers)

    def preview(self, rows, allowed=None):
        return roster.build_preview(self.headers, rows, self.mapping, allowed)

    def test_reads_the_customers_own_sample_rows(self):
        rows = [
            ['John', 'Doe', 'john.doe@example.com', 'Literature, CiteSource',
             'Admin', 'Yes', 'Yes', ''],
            ['Jane', 'Smith', 'jane.smith@example.com', 'Ready View, Vigilance',
             'Fulfiller/ Edit', 'No', 'No', ''],
        ]
        out = self.preview(rows)
        self.assertEqual(out[0]['email'], 'john.doe@example.com')
        self.assertEqual(out[0]['modules'], ['literature', 'citesource'])
        self.assertEqual(out[0]['role_type'], RequestedUser.ROLE_ADMIN)
        self.assertEqual(out[1]['role_type'], RequestedUser.ROLE_FULFILLER)
        self.assertTrue(all(r['importable'] for r in out))

    def test_the_yes_in_the_status_columns_is_not_read_as_anything(self):
        # The sample rows above say "Yes" under both status columns. Nothing in
        # the parsed output may carry it.
        out = self.preview([['A', 'B', 'a@x.com', 'Literature', 'Admin',
                             'Yes', 'Yes', '']])
        self.assertNotIn('added_at', out[0])
        self.assertNotIn('activation_email_sent_at', out[0])

    def test_row_numbers_match_what_they_see_in_excel(self):
        out = self.preview([['A', 'B', 'a@x.com', '', 'Admin', '', '', '']])
        self.assertEqual(out[0]['line'], 2)  # row 1 is the header

    def test_a_row_with_no_email_cannot_be_imported(self):
        out = self.preview([['A', 'B', '', 'Literature', 'Admin', '', '', '']])
        self.assertFalse(out[0]['importable'])
        self.assertTrue(any(p['field'] == roster.FIELD_EMAIL
                            for p in out[0]['problems']))

    def test_duplicate_email_is_flagged_and_names_the_earlier_row(self):
        out = self.preview([
            ['A', 'B', 'dup@x.com', '', 'Admin', '', '', ''],
            ['C', 'D', 'dup@x.com', '', 'Viewer', '', '', ''],
        ])
        message = out[1]['problems'][0]['message']
        self.assertIn('row 2', message)
        # Still importable — the later row wins, which is what update_or_create
        # does, so warning is right and refusing would be wrong.
        self.assertTrue(out[1]['importable'])

    def test_missing_role_defaults_to_viewer_and_says_so(self):
        out = self.preview([['A', 'B', 'a@x.com', 'Literature', '', '', '', '']])
        self.assertEqual(out[0]['role_type'], RequestedUser.ROLE_VIEWER)
        self.assertTrue(any('Viewer' in p['message'] for p in out[0]['problems']))

    def test_full_name_column_is_used_when_there_are_no_split_names(self):
        headers = ['Name', 'Email']
        out = roster.build_preview(
            headers, [['Anna Lee', 'anna@x.com']],
            roster.sniff_mapping(headers))
        self.assertEqual((out[0]['first_name'], out[0]['last_name']),
                         ('Anna', 'Lee'))


class TemplateCsvTests(TestCase):
    def test_the_template_round_trips_through_our_own_parser(self):
        # If the file we hand out does not import cleanly, nothing else matters.
        headers, rows = roster.parse_file('t.csv', roster.template_csv().encode())
        mapping = roster.sniff_mapping(headers)
        out = roster.build_preview(headers, rows, mapping)
        self.assertEqual(len(out), len(roster.TEMPLATE_SAMPLE_ROWS))
        self.assertTrue(all(r['importable'] for r in out))
        self.assertTrue(all(not any(p['field'] == roster.FIELD_MODULES
                                    for p in r['problems']) for r in out))


# ── The form ─────────────────────────────────────────────────────────────────

class RosterTestBase(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.rival = Company.objects.create(name='Rival')
        # Customers, deliberately: in this app PortalUser.role='admin' is a
        # CiteMed staff agent, so a customer fixture carrying it would silently
        # pass every require_portal_admin gate and make the tenancy tests lie.
        self.jane = PortalUser.objects.create(
            email='jane@acme.com', name='Jane', company=self.acme,
            role=PortalUser.ROLE_CUSTOMER)
        self.outsider = PortalUser.objects.create(
            email='bob@rival.com', company=self.rival,
            role=PortalUser.ROLE_CUSTOMER)
        self.staff = PortalUser.objects.create(
            email='csm@citemed.com', name='Ana', company=None,
            role=PortalUser.ROLE_ADMIN)
        self.request = UserRequest.objects.create(
            company=self.acme, status=UserRequest.STATUS_SENT,
            sent_at=timezone.now(), created_by=self.staff)
        self.login(self.jane)

    def login(self, user):
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def add(self, **kwargs):
        payload = {'email': 'new@acme.com', 'first_name': 'New',
                   'last_name': 'Person', 'modules': ['literature'],
                   'role_type': 'viewer'}
        payload.update(kwargs)
        return self.client.post('/api/roster/users/',
                                data=json.dumps(payload),
                                content_type='application/json')


class FormReadTests(RosterTestBase):
    def test_returns_the_open_request_for_my_company(self):
        res = self.client.get('/api/roster/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['request']['id'], self.request.id)

    def test_another_companys_request_is_invisible(self):
        self.login(self.outsider)
        res = self.client.get('/api/roster/')
        self.assertIsNone(res.json()['request'])

    def test_module_options_come_from_the_company_not_a_hardcoded_list(self):
        self.acme.licensed_modules = ['literature', 'pathways']
        self.acme.save(update_fields=['licensed_modules'])
        res = self.client.get('/api/roster/')
        keys = [m['key'] for m in res.json()['request']['module_options']]
        self.assertEqual(keys, ['literature', 'pathways'])

    def test_no_entitlement_recorded_means_everything_is_offered(self):
        res = self.client.get('/api/roster/')
        keys = [m['key'] for m in res.json()['request']['module_options']]
        self.assertEqual(len(keys), 5)

    def test_anonymous_is_refused(self):
        self.client.session.flush()
        fresh = self.client_class()
        self.assertEqual(fresh.get('/api/roster/').status_code, 401)


class FormWriteTests(RosterTestBase):
    def test_adds_a_person(self):
        res = self.add()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.request.users.count(), 1)

    def test_adding_the_same_address_twice_corrects_rather_than_duplicates(self):
        self.add(role_type='viewer')
        res = self.add(role_type='admin')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.request.users.count(), 1)
        self.assertEqual(self.request.users.first().role_type, 'admin')

    def test_a_module_they_are_not_licensed_for_is_dropped_not_trusted(self):
        # The picker only offers licensed modules, but the picker is not the
        # security boundary — a hand-rolled POST must not widen access.
        self.acme.licensed_modules = ['literature']
        self.acme.save(update_fields=['licensed_modules'])
        self.add(modules=['literature', 'pathways'])
        self.assertEqual(self.request.users.first().modules, ['literature'])

    def test_an_unknown_role_falls_back_to_the_least_privilege_one(self):
        self.add(role_type='superuser')
        self.assertEqual(self.request.users.first().role_type,
                         RequestedUser.ROLE_VIEWER)

    def test_status_columns_cannot_be_posted(self):
        # The single most important assertion in this file.
        self.add(added_at=timezone.now().isoformat(),
                 activation_email_sent_at=timezone.now().isoformat())
        row = self.request.users.first()
        self.assertIsNone(row.added_at)
        self.assertIsNone(row.activation_email_sent_at)

    def test_a_bad_address_is_refused(self):
        self.assertEqual(self.add(email='not-an-email').status_code, 400)

    def test_cannot_add_to_another_companys_roster(self):
        self.login(self.outsider)
        self.assertEqual(self.add().status_code, 404)

    def test_edit_and_delete(self):
        self.add()
        row = self.request.users.first()
        res = self.client.patch(f'/api/roster/users/{row.id}/',
                                data=json.dumps({'first_name': 'Changed'}),
                                content_type='application/json')
        self.assertEqual(res.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.first_name, 'Changed')

        res = self.client.delete(f'/api/roster/users/{row.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.request.users.count(), 0)

    def test_cannot_delete_somebody_already_provisioned(self):
        # Removing the row would hide a person who actually has access.
        self.add()
        row = self.request.users.first()
        row.added_at = timezone.now()
        row.save(update_fields=['added_at'])
        res = self.client.delete(f'/api/roster/users/{row.id}/')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.request.users.count(), 1)

    def test_another_companys_row_does_not_resolve(self):
        self.add()
        row = self.request.users.first()
        self.login(self.outsider)
        res = self.client.patch(f'/api/roster/users/{row.id}/',
                                data=json.dumps({'first_name': 'Hacked'}),
                                content_type='application/json')
        self.assertEqual(res.status_code, 404)


class SubmitTests(RosterTestBase):
    def test_submitting_locks_the_form(self):
        self.add()
        res = self.client.post('/api/roster/submit/')
        self.assertEqual(res.status_code, 200)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, UserRequest.STATUS_SUBMITTED)
        # And further edits are refused.
        self.assertEqual(self.add(email='late@acme.com').status_code, 409)

    def test_cannot_submit_an_empty_roster(self):
        self.assertEqual(self.client.post('/api/roster/submit/').status_code, 400)

    def test_cannot_submit_while_an_import_is_still_running(self):
        self.add()
        RosterImport.objects.create(
            request=self.request, filename='r.csv',
            state=RosterImport.STATE_CONFIRMED)
        self.assertEqual(self.client.post('/api/roster/submit/').status_code, 409)


class TemplateDownloadTests(RosterTestBase):
    def test_serves_a_csv_with_the_expected_headings(self):
        res = self.client.get('/api/roster/template.csv')
        self.assertEqual(res.status_code, 200)
        self.assertIn('attachment', res['Content-Disposition'])
        rows = list(csv.reader(io.StringIO(res.content.decode())))
        self.assertEqual(rows[0], roster.TEMPLATE_HEADERS)


# ── Import ───────────────────────────────────────────────────────────────────

SHEET = (
    'First Name,Last Name,Email,Modules,Role Type,'
    'Activation Email Sent?,Added?,Notes\n'
    'John,Doe,john.doe@example.com,"Literature, CiteSource",Admin,Yes,Yes,\n'
    'Jane,Smith,jane.smith@example.com,"Ready View, Vigilance",Fulfiller/ Edit,No,No,\n'
    'Anna,Lee,anna.lee@example.com,Pathways,Viewer,Yes,No,\n'
)


class ImportTests(RosterTestBase):
    def upload_file(self, text=SHEET, name='roster.csv'):
        buf = io.BytesIO(text.encode())
        buf.name = name
        return self.client.post('/api/roster/imports/', {'file': buf})

    def test_upload_previews_without_writing_anybody(self):
        res = self.upload_file()
        self.assertEqual(res.status_code, 201)
        body = res.json()['import']
        self.assertEqual(body['state'], RosterImport.STATE_PENDING_REVIEW)
        self.assertEqual(len(body['preview']), 3)
        # Nothing on the roster yet: the confirmation step has not happened.
        self.assertEqual(self.request.users.count(), 0)

    def test_preview_shows_the_mapping_it_guessed(self):
        body = self.upload_file().json()['import']
        self.assertEqual(body['mapping']['2'], roster.FIELD_EMAIL)
        self.assertEqual(body['unmapped_headers'], [])

    def test_confirming_queues_it_rather_than_applying_it(self):
        job_id = self.upload_file().json()['import']['id']
        res = self.client.post(f'/api/roster/imports/{job_id}/',
                               data=json.dumps({'confirm': True}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        job = RosterImport.objects.get(pk=job_id)
        self.assertEqual(job.state, RosterImport.STATE_CONFIRMED)
        self.assertEqual(self.request.users.count(), 0)

    def test_the_cron_command_applies_it(self):
        job_id = self.upload_file().json()['import']['id']
        self.client.post(f'/api/roster/imports/{job_id}/',
                         data=json.dumps({'confirm': True}),
                         content_type='application/json')
        call_command('process_roster_imports')

        job = RosterImport.objects.get(pk=job_id)
        self.assertEqual(job.state, RosterImport.STATE_DONE)
        self.assertEqual(job.created_count, 3)
        self.assertEqual(self.request.users.count(), 3)

        john = self.request.users.get(email='john.doe@example.com')
        self.assertEqual(john.modules, ['literature', 'citesource'])
        self.assertEqual(john.role_type, RequestedUser.ROLE_ADMIN)
        self.assertEqual(john.source, RequestedUser.SOURCE_IMPORT)

    def test_the_yes_columns_in_the_file_do_not_mark_anybody_provisioned(self):
        # The sheet says "Added? Yes" for John. It is not our source for that.
        job_id = self.upload_file().json()['import']['id']
        self.client.post(f'/api/roster/imports/{job_id}/',
                         data=json.dumps({'confirm': True}),
                         content_type='application/json')
        call_command('process_roster_imports')
        john = self.request.users.get(email='john.doe@example.com')
        self.assertIsNone(john.added_at)
        self.assertIsNone(john.activation_email_sent_at)

    def test_re_uploading_a_corrected_sheet_updates_rather_than_doubles(self):
        for text in (SHEET, SHEET.replace('Viewer', 'Admin')):
            job_id = self.upload_file(text).json()['import']['id']
            self.client.post(f'/api/roster/imports/{job_id}/',
                             data=json.dumps({'confirm': True}),
                             content_type='application/json')
            call_command('process_roster_imports')
        self.assertEqual(self.request.users.count(), 3)
        self.assertEqual(
            self.request.users.get(email='anna.lee@example.com').role_type,
            RequestedUser.ROLE_ADMIN)

    def test_confirming_without_an_email_column_is_refused(self):
        job_id = self.upload_file('Name,Role\nAnna,Viewer\n').json()['import']['id']
        res = self.client.post(f'/api/roster/imports/{job_id}/',
                               data=json.dumps({'confirm': True}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_a_corrected_mapping_is_what_gets_applied(self):
        # The confirmation step is only meaningful if the correction survives
        # to the apply. Header says "Contact" (unmapped); the human points it
        # at the email column.
        text = 'Contact,Role Type\nanna@x.com,Viewer\n'
        job_id = self.upload_file(text).json()['import']['id']
        self.client.post(
            f'/api/roster/imports/{job_id}/',
            data=json.dumps({'mapping': {'0': roster.FIELD_EMAIL,
                                         '1': roster.FIELD_ROLE},
                             'confirm': True}),
            content_type='application/json')
        call_command('process_roster_imports')
        self.assertEqual(self.request.users.count(), 1)
        self.assertEqual(self.request.users.first().email, 'anna@x.com')

    def test_rows_without_an_email_are_skipped_and_reported(self):
        text = ('First Name,Email\n'
                'Anna,anna@x.com\n'
                'Nobody,\n')
        job_id = self.upload_file(text).json()['import']['id']
        self.client.post(f'/api/roster/imports/{job_id}/',
                         data=json.dumps({'confirm': True}),
                         content_type='application/json')
        call_command('process_roster_imports')
        job = RosterImport.objects.get(pk=job_id)
        self.assertEqual(job.created_count, 1)
        self.assertEqual(job.skipped_count, 1)
        self.assertTrue(any(p['row'] == 3 for p in job.problems))

    def test_two_concurrent_runs_cannot_both_apply_one_import(self):
        job_id = self.upload_file().json()['import']['id']
        self.client.post(f'/api/roster/imports/{job_id}/',
                         data=json.dumps({'confirm': True}),
                         content_type='application/json')
        call_command('process_roster_imports')
        # A second pass must find nothing to do rather than re-apply.
        call_command('process_roster_imports')
        job = RosterImport.objects.get(pk=job_id)
        self.assertEqual(job.created_count, 3)
        self.assertEqual(self.request.users.count(), 3)

    def test_dry_run_writes_nothing(self):
        job_id = self.upload_file().json()['import']['id']
        self.client.post(f'/api/roster/imports/{job_id}/',
                         data=json.dumps({'confirm': True}),
                         content_type='application/json')
        call_command('process_roster_imports', dry_run=True)
        self.assertEqual(RosterImport.objects.get(pk=job_id).state,
                         RosterImport.STATE_CONFIRMED)
        self.assertEqual(self.request.users.count(), 0)

    def test_another_companys_import_does_not_resolve(self):
        job_id = self.upload_file().json()['import']['id']
        self.login(self.outsider)
        res = self.client.get(f'/api/roster/imports/{job_id}/')
        self.assertEqual(res.status_code, 404)


# ── Provisioning, and the rule that it never emails ──────────────────────────

class ProvisionTests(RosterTestBase):
    def setUp(self):
        super().setUp()
        self.row = RequestedUser.objects.create(
            request=self.request, email='anna.lee@example.com',
            first_name='Anna', last_name='Lee',
            modules=['literature'], role_type=RequestedUser.ROLE_FULFILLER)
        self.login(self.staff)

    def provision(self):
        return self.client.post(
            f'/api/admin/roster/requests/{self.request.id}/',
            data=json.dumps({'action': 'provision'}),
            content_type='application/json')

    def test_creates_a_portal_user(self):
        mail.outbox = []
        res = self.provision()
        self.assertEqual(res.status_code, 200)
        user = PortalUser.objects.get(email='anna.lee@example.com')
        self.assertEqual(user.company, self.acme)
        self.assertEqual(user.name, 'Anna Lee')

    def test_provisioning_sends_absolutely_nothing(self):
        # REV-26's first rule. The only version of it that means anything is a
        # test that reads the mailbox.
        mail.outbox = []
        self.provision()
        self.assertEqual(len(mail.outbox), 0)

    def test_it_stamps_added_at_and_leaves_the_invite_column_alone(self):
        self.provision()
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.added_at)
        self.assertIsNone(self.row.activation_email_sent_at)

    def test_the_customer_facing_role_maps_to_the_portals_own(self):
        self.provision()
        self.assertEqual(
            PortalUser.objects.get(email='anna.lee@example.com').role,
            PortalUser.ROLE_CUSTOMER)

    def test_a_customers_admin_does_not_become_a_citemed_staff_agent(self):
        # PortalUser.role='admin' is a STAFF role in this app: it passes
        # require_portal_admin (every company's tickets and files) and lands in
        # ticket_notify.agent_emails(). A customer must not be able to grant
        # themselves that by typing "Admin" in their own spreadsheet.
        self.row.role_type = RequestedUser.ROLE_ADMIN
        self.row.save(update_fields=['role_type'])
        self.provision()
        user = PortalUser.objects.get(email='anna.lee@example.com')
        self.assertEqual(user.role, PortalUser.ROLE_CUSTOMER)
        self.assertNotEqual(user.role, PortalUser.ROLE_ADMIN)
        self.assertNotEqual(user.role, PortalUser.ROLE_OWNER)
        # The customer's own word for it is not lost — it is what Evidence
        # Cloud provisioning reads, and what staff read before promoting
        # anybody by hand.
        self.row.refresh_from_db()
        self.assertEqual(self.row.role_type, RequestedUser.ROLE_ADMIN)

    def test_re_running_does_not_duplicate_or_restate_when_they_joined(self):
        self.provision()
        self.row.refresh_from_db()
        first = self.row.added_at
        self.provision()
        self.row.refresh_from_db()
        self.assertEqual(self.row.added_at, first)
        self.assertEqual(
            PortalUser.objects.filter(email='anna.lee@example.com').count(), 1)

    def test_an_address_owned_by_another_company_is_refused_not_reassigned(self):
        PortalUser.objects.create(email='anna.lee@example.com',
                                  company=self.rival)
        res = self.provision()
        self.assertEqual(res.json()['result']['skipped'], 1)
        self.assertEqual(
            PortalUser.objects.get(email='anna.lee@example.com').company,
            self.rival)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.added_at)

    def test_a_customer_cannot_provision(self):
        self.login(self.jane)
        self.assertEqual(self.provision().status_code, 403)


class InviteTests(RosterTestBase):
    def setUp(self):
        super().setUp()
        self.row = RequestedUser.objects.create(
            request=self.request, email='anna.lee@example.com',
            first_name='Anna', last_name='Lee', modules=['literature'])
        self.login(self.staff)
        self.client.post(f'/api/admin/roster/requests/{self.request.id}/',
                         data=json.dumps({'action': 'provision'}),
                         content_type='application/json')
        mail.outbox = []

    def invite(self, **extra):
        return self.client.post(
            f'/api/admin/roster/requests/{self.request.id}/',
            data=json.dumps({'action': 'invite', **extra}),
            content_type='application/json')

    def test_sends_one_email_and_records_that_it_went(self):
        res = self.invite()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('anna.lee@example.com', mail.outbox[0].to)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.activation_email_sent_at)

    def test_the_invite_carries_a_working_sign_in_link(self):
        self.invite()
        body = mail.outbox[0].body
        self.assertIn('/auth/verify?token=', body)

    def test_it_names_what_they_were_given(self):
        self.invite()
        self.assertIn('Literature', mail.outbox[0].body)

    def test_pressing_invite_twice_does_not_mail_anybody_twice(self):
        self.invite()
        mail.outbox = []
        self.invite()
        self.assertEqual(len(mail.outbox), 0)

    def test_naming_somebody_explicitly_re_sends_to_just_them(self):
        self.invite()
        mail.outbox = []
        self.invite(user_ids=[self.row.id])
        self.assertEqual(len(mail.outbox), 1)

    def test_somebody_never_provisioned_is_not_invited(self):
        RequestedUser.objects.create(
            request=self.request, email='ghost@example.com')
        self.invite()
        recipients = [addr for m in mail.outbox for addr in m.to]
        self.assertNotIn('ghost@example.com', recipients)


class StatusNoteTests(RosterTestBase):
    def test_the_override_annotates_and_never_overwrites_the_timestamps(self):
        row = RequestedUser.objects.create(
            request=self.request, email='anna@x.com')
        self.login(self.staff)
        res = self.client.post(
            f'/api/admin/roster/users/{row.id}/note',
            data=json.dumps({'note': 'Invited by hand from Outlook on 3 Sep.'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        row.refresh_from_db()
        self.assertIn('Outlook', row.status_note)
        # "We emailed them ourselves" must stay distinguishable from
        # "the system sent it".
        self.assertIsNone(row.activation_email_sent_at)
        self.assertEqual(row.status_overridden_by, self.staff)


class AdminRequestTests(RosterTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.staff)

    def test_lists_requests_with_counts(self):
        RequestedUser.objects.create(request=self.request, email='a@x.com',
                                     added_at=timezone.now())
        res = self.client.get('/api/admin/roster/requests/')
        row = res.json()['requests'][0]
        self.assertEqual(row['user_count'], 1)
        self.assertEqual(row['added_count'], 1)
        self.assertEqual(row['invited_count'], 0)

    def test_refuses_a_second_open_request_for_one_company(self):
        res = self.client.post('/api/admin/roster/requests/',
                               data=json.dumps({'company_id': self.acme.id}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 409)

    def test_opens_one_for_a_company_that_has_none(self):
        res = self.client.post('/api/admin/roster/requests/',
                               data=json.dumps({'company_id': self.rival.id}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['request']['status'], UserRequest.STATUS_SENT)

    def test_reopening_lets_the_customer_edit_again(self):
        self.request.status = UserRequest.STATUS_SUBMITTED
        self.request.save(update_fields=['status'])
        self.client.post(f'/api/admin/roster/requests/{self.request.id}/',
                         data=json.dumps({'action': 'reopen'}),
                         content_type='application/json')
        self.request.refresh_from_db()
        self.assertTrue(self.request.is_customer_editable)

    def test_a_customer_cannot_reach_the_admin_list(self):
        self.login(self.jane)
        self.assertEqual(
            self.client.get('/api/admin/roster/requests/').status_code, 403)

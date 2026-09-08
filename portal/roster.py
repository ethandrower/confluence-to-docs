"""Reading a customer's roster spreadsheet (REV-45).

All of the interesting behaviour of the import lives here as pure functions over
plain data, with no model and no request in sight, because every hard case in a
spreadsheet import is a parsing case: a header spelled a third way, a role typed
in prose, five modules in one cell, the same person twice. Those are cheap to
test exhaustively and expensive to debug through a view.

THE SHAPE WE ARE READING. The customer's own template looks like this:

    First Name | Last Name | Email | Modules | Role Type |
    Activation Email Sent? | Added? | Notes

Two of those columns are ours, not theirs. "Activation Email Sent?" and "Added?"
describe what WE did, and are derived from the provisioning run — so they are
recognised (a customer's sheet will have them, and calling a column they were
told to use "unrecognised" is a bug) and then deliberately not imported. See
IGNORED_FIELDS.
"""
import csv
import io
import re

from portal.models import MODULE_KEYS, MODULE_LABELS, RequestedUser

def _slug(text):
    """Lowercase, strip everything that is not a letter or a digit.

    Deliberately aggressive: it is what collapses "Role Type", "role_type",
    "Role-Type" and "ROLE TYPE " onto one key, and it is why the alias tables
    below can stay short. Defined first because they are built with it.
    """
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


#: Canonical field names the importer understands.
FIELD_FIRST_NAME = 'first_name'
FIELD_LAST_NAME = 'last_name'
FIELD_FULL_NAME = 'full_name'
FIELD_EMAIL = 'email'
FIELD_MODULES = 'modules'
FIELD_ROLE = 'role_type'
FIELD_NOTE = 'note'
#: Recognised so they are not reported as unknown, then dropped. Status is ours.
FIELD_IGNORED_STATUS = '_status_ignored'

IGNORED_FIELDS = {FIELD_IGNORED_STATUS}

#: Only this one makes a row worth keeping. Everything else can be blank.
REQUIRED_FIELDS = {FIELD_EMAIL}

FIELD_LABELS = {
    FIELD_FIRST_NAME: 'First name',
    FIELD_LAST_NAME: 'Last name',
    FIELD_FULL_NAME: 'Full name',
    FIELD_EMAIL: 'Email',
    FIELD_MODULES: 'Modules',
    FIELD_ROLE: 'Role type',
    FIELD_NOTE: 'Notes',
    FIELD_IGNORED_STATUS: 'Status (not imported — we set this)',
}

#: Header text -> field, matched after _slug(). Several spellings per field
#: because the sheet that comes back is rarely the sheet that went out: people
#: rename columns, translate them, and paste from their own HR export.
HEADER_ALIASES = {
    'firstname': FIELD_FIRST_NAME,
    'first': FIELD_FIRST_NAME,
    'givenname': FIELD_FIRST_NAME,
    'forename': FIELD_FIRST_NAME,
    'lastname': FIELD_LAST_NAME,
    'last': FIELD_LAST_NAME,
    'surname': FIELD_LAST_NAME,
    'familyname': FIELD_LAST_NAME,
    'name': FIELD_FULL_NAME,
    'fullname': FIELD_FULL_NAME,
    'username': FIELD_FULL_NAME,
    'email': FIELD_EMAIL,
    'emailaddress': FIELD_EMAIL,
    'mail': FIELD_EMAIL,
    'workemail': FIELD_EMAIL,
    'modules': FIELD_MODULES,
    'module': FIELD_MODULES,
    'moduleaccess': FIELD_MODULES,
    'products': FIELD_MODULES,
    'licenses': FIELD_MODULES,
    'licences': FIELD_MODULES,
    'roletype': FIELD_ROLE,
    'role': FIELD_ROLE,
    'accesstype': FIELD_ROLE,
    'permission': FIELD_ROLE,
    'permissions': FIELD_ROLE,
    'notes': FIELD_NOTE,
    'note': FIELD_NOTE,
    'comment': FIELD_NOTE,
    'comments': FIELD_NOTE,
    # Ours. Recognised, then dropped.
    'activationemailsent': FIELD_IGNORED_STATUS,
    'activationemail': FIELD_IGNORED_STATUS,
    'invited': FIELD_IGNORED_STATUS,
    'invitesent': FIELD_IGNORED_STATUS,
    'added': FIELD_IGNORED_STATUS,
    'status': FIELD_IGNORED_STATUS,
    'provisioned': FIELD_IGNORED_STATUS,
}

#: Role text -> RequestedUser.ROLE_*. Keys are _slug()ed, which is what lets
#: "Fulfiller/ Edit" (the stray space in the customer's own template) and
#: "Fulfiller / Edit" and "fulfiller-edit" all land on the same role.
ROLE_ALIASES = {
    'admin': RequestedUser.ROLE_ADMIN,
    'administrator': RequestedUser.ROLE_ADMIN,
    'owner': RequestedUser.ROLE_ADMIN,
    'fulfilleredit': RequestedUser.ROLE_FULFILLER,
    'fulfiller': RequestedUser.ROLE_FULFILLER,
    'edit': RequestedUser.ROLE_FULFILLER,
    'editor': RequestedUser.ROLE_FULFILLER,
    'writer': RequestedUser.ROLE_FULFILLER,
    'contributor': RequestedUser.ROLE_FULFILLER,
    'viewer': RequestedUser.ROLE_VIEWER,
    'view': RequestedUser.ROLE_VIEWER,
    'readonly': RequestedUser.ROLE_VIEWER,
    'read': RequestedUser.ROLE_VIEWER,
    'reader': RequestedUser.ROLE_VIEWER,
}

#: Module text -> key. Built from the canonical labels, plus the spellings that
#: turn up in practice — "ReadyView" as one word being the obvious one.
MODULE_ALIASES = {_slug(label): key for key, label in MODULE_LABELS.items()}
MODULE_ALIASES.update({
    'readyview': 'readyview',
    'ready': 'readyview',
    'rv': 'readyview',
    'lit': 'literature',
    'literaturereview': 'literature',
    'cite': 'citesource',
    'source': 'citesource',
    'vig': 'vigilance',
    'pmcf': 'vigilance',
    'pathway': 'pathways',
})

#: What a module cell may be separated by. Semicolons and pipes show up when
#: somebody's spreadsheet already treats the comma as a column separator.
MODULE_SPLIT = re.compile(r'[,;|/]| and ')

#: The template we hand out. Column order matches what the customer was sent,
#: status columns included, so the file they send back round-trips unchanged.
TEMPLATE_HEADERS = ['First Name', 'Last Name', 'Email', 'Modules', 'Role Type',
                    'Activation Email Sent?', 'Added?', 'Notes']

TEMPLATE_SAMPLE_ROWS = [
    ['Jane', 'Smith', 'jane.smith@example.com', 'Literature, CiteSource',
     'Admin', '', '', 'Primary contact'],
    ['Carlos', 'Mendez', 'carlos.mendez@example.com', 'Ready View, Vigilance',
     'Fulfiller / Edit', '', '', ''],
    ['Anna', 'Lee', 'anna.lee@example.com', 'Pathways', 'Viewer', '', '', ''],
]


# ── Reading the file ─────────────────────────────────────────────────────────

class RosterParseError(Exception):
    """The file could not be read at all. Distinct from a row being wrong:
    this one has no preview to show, so the caller reports it and stops."""


def parse_file(filename, content):
    """(headers, rows) from CSV or XLSX bytes.

    Chooses on the file extension rather than sniffing the bytes, because the
    two formats are unmistakable to the libraries and a mislabelled file is
    better reported than guessed at.
    """
    name = (filename or '').lower()
    if name.endswith(('.xlsx', '.xlsm')):
        return _parse_xlsx(content)
    if name.endswith('.xls'):
        raise RosterParseError(
            'The old .xls format is not supported. Save as .xlsx or CSV and '
            'upload again.')
    return _parse_csv(content)


def _parse_csv(content):
    if isinstance(content, bytes):
        # utf-8-sig, because Excel's "CSV UTF-8" writes a BOM and it would
        # otherwise ride along on the first header and break the match.
        for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise RosterParseError('Could not read the file as text.')
    else:
        text = content

    try:
        # Sniffing the dialect handles the semicolon-separated CSVs that some
        # European Excel locales produce by default.
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows = [[(c or '').strip() for c in row] for row in reader]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        raise RosterParseError('The file is empty.')
    return rows[0], rows[1:]


def _parse_xlsx(content):
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - dependency is declared
        raise RosterParseError(
            'Excel files cannot be read on this server. Save as CSV instead.')

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise RosterParseError(f'Could not read the spreadsheet: {exc}')

    ws = wb[wb.sheetnames[0]]
    rows = []
    for raw in ws.iter_rows(values_only=True):
        cells = ['' if c is None else str(c).strip() for c in raw]
        if any(cells):
            rows.append(cells)
    wb.close()
    if not rows:
        raise RosterParseError('The spreadsheet is empty.')

    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    return rows[0], rows[1:]


# ── Working out what the columns mean ────────────────────────────────────────

def sniff_mapping(headers):
    """Guess {column index as str -> field} from the header row.

    Keys are strings because this is stored in a JSONField and round-trips
    through JSON, where object keys are always strings. Keeping the stored form
    and the in-memory form identical avoids a class of bug where the mapping
    works before a save and silently misses after one.

    A field claimed by an earlier column wins: given both "Name" and "First
    Name", the more specific header should not be overwritten by the vaguer one
    appearing later.
    """
    mapping = {}
    claimed = set()
    for index, header in enumerate(headers or []):
        field = HEADER_ALIASES.get(_slug(header))
        if field and (field in IGNORED_FIELDS or field not in claimed):
            mapping[str(index)] = field
            claimed.add(field)
    return mapping


def unmapped_headers(headers, mapping):
    """Headers the mapping does not use — what the confirmation step warns about."""
    return [h for i, h in enumerate(headers or []) if not mapping.get(str(i))]


# ── Normalising one cell ─────────────────────────────────────────────────────

def normalise_email(value):
    return str(value or '').strip().lower()


def normalise_role(value):
    """Role key, or None if the text means nothing to us.

    None rather than a default: silently filing an unreadable role as Viewer
    would hand somebody the wrong access with no warning anywhere. The caller
    turns it into a row-level problem the human has to look at.
    """
    if not str(value or '').strip():
        return None
    return ROLE_ALIASES.get(_slug(value))


def normalise_modules(value, allowed=None):
    """(recognised keys, unrecognised fragments) from one Modules cell.

    Order follows MODULE_KEYS rather than the order they were typed, so two
    rows listing the same modules differently compare equal.
    """
    text = str(value or '').strip()
    if not text:
        return [], []

    keys, unknown = set(), []
    for fragment in MODULE_SPLIT.split(text):
        fragment = fragment.strip()
        if not fragment:
            continue
        key = MODULE_ALIASES.get(_slug(fragment))
        if key is None:
            unknown.append(fragment)
        elif allowed is not None and key not in allowed:
            # Recognised, but not something this customer is licensed for.
            # Reported in their own words so the message names what they typed.
            unknown.append(fragment)
        else:
            keys.add(key)

    ordered = [k for k in MODULE_KEYS if k in keys]
    return ordered, unknown


def split_full_name(value):
    """('First', 'Last') from a single name cell. Last word is the surname."""
    parts = str(value or '').strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return ' '.join(parts[:-1]), parts[-1]


# ── Turning the sheet into rows we could save ────────────────────────────────

def build_preview(headers, rows, mapping, allowed_modules=None):
    """What the confirmation step renders, and what the applier later writes.

    One dict per input row: the cleaned values, plus any problems found. Both
    phases call this, so what a human confirms is exactly what gets applied —
    if the preview and the write did their own parsing they would drift, and the
    confirmation step would be theatre.

    Row numbers are 1-based and count the header, so they match what the person
    sees in Excel when they go to fix it.
    """
    allowed = list(allowed_modules) if allowed_modules is not None else None
    by_field = {}
    for index, field in (mapping or {}).items():
        if field and field not in IGNORED_FIELDS:
            by_field.setdefault(field, int(index))

    def cell(row, field):
        index = by_field.get(field)
        if index is None or index >= len(row):
            return ''
        return str(row[index] or '').strip()

    preview, seen_emails = [], {}
    for offset, row in enumerate(rows or []):
        line = offset + 2  # +1 for zero-index, +1 for the header row
        problems = []

        email = normalise_email(cell(row, FIELD_EMAIL))
        first = cell(row, FIELD_FIRST_NAME)
        last = cell(row, FIELD_LAST_NAME)
        if not first and not last:
            first, last = split_full_name(cell(row, FIELD_FULL_NAME))

        if not email:
            problems.append({'field': FIELD_EMAIL,
                             'message': 'No email address, so this row cannot be imported.'})
        elif '@' not in email or email.startswith('@') or email.endswith('@'):
            problems.append({'field': FIELD_EMAIL,
                             'message': f'"{email}" does not look like an email address.'})
        elif email in seen_emails:
            problems.append({
                'field': FIELD_EMAIL,
                'message': f'{email} also appears on row {seen_emails[email]}. '
                           f'Only the last one will be kept.'})

        role = normalise_role(cell(row, FIELD_ROLE))
        raw_role = cell(row, FIELD_ROLE)
        if raw_role and role is None:
            problems.append({
                'field': FIELD_ROLE,
                'message': f'"{raw_role}" is not a role we recognise. '
                           f'Choose Admin, Fulfiller / Edit or Viewer.'})
        if not raw_role:
            problems.append({'field': FIELD_ROLE,
                             'message': 'No role given — defaults to Viewer.'})

        modules, unknown = normalise_modules(cell(row, FIELD_MODULES), allowed)
        for fragment in unknown:
            problems.append({
                'field': FIELD_MODULES,
                'message': f'"{fragment}" is not a module available to you.'})

        if email:
            seen_emails[email] = line

        preview.append({
            'line': line,
            'first_name': first,
            'last_name': last,
            'email': email,
            'modules': modules,
            'role_type': role or RequestedUser.ROLE_VIEWER,
            'note': cell(row, FIELD_NOTE),
            'problems': problems,
            # A row is importable when it has an address to import it under.
            # Everything else degrades to a default and says so.
            'importable': bool(email) and not any(
                p['field'] == FIELD_EMAIL and 'also appears' not in p['message']
                for p in problems),
        })
    return preview


def template_csv():
    """The downloadable template, as CSV text."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(TEMPLATE_HEADERS)
    for row in TEMPLATE_SAMPLE_ROWS:
        writer.writerow(row)
    return out.getvalue()

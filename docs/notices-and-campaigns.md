# Notices, and sending things to people

Scoping note, 2026-09-02. Nothing here is built yet.

Three asks, in the order they came up:

1. A notice banner should be clickable — read more detail than one line.
2. We need to send campaigns and updates: maintenance, product updates.
3. It should use the branded HTML template the other emails use.

They are closer together than they look. All three are "we have something to
say to a set of customers, and one line in a banner is not enough."

## What exists today

`SiteNotice` (portal/models.py) is an incident/maintenance banner:

- `level` (info / warning / critical), `message`, optional `link_url` + `link_label`
- an active window (`starts_at`, `ends_at`), and `retired_at` instead of deletion
- `companies` M2M — empty means everyone
- `NoticeDismissal`, one per (user, notice); critical notices refuse to dismiss

It renders in `SiteNoticeBanner.vue` inside the app shell, pushed live over
`/ws/notices/`, and there is a `/notices` history page.

**It sends no email.** `notices_admin._notify` calls only
`realtime.notify_notice`. That is the whole notification path.

This is not an oversight nobody noticed — it is written down in the code. The
model docstring and `views/notices.py` both say that EC-SOP-07 §5.2 names email
to the designated account contact as the channel, and that the banner
*supplements* that email and never replaces it. Only the supplement was built.

Two consequences worth stating plainly, because they are the argument for
doing this work:

- **The one channel we have shares fate with the thing it reports on.** One
  host, one web container. During a SEV-1 the portal is down, so the banner
  cannot render — precisely when there is something to say.
- **A customer only learns of an incident if they happen to sign in.** Nobody
  is told anything. They discover it by walking into it.

Both are now recorded as `known-defect` cases in `qa/qase/support-portal-cases.yaml`.

## 1. Clickable notice, with a detail view

`message` is currently the entire content, and it renders in a banner, so it
has to stay one line. That is the constraint to remove.

- Add `detail` — the long form. What is affected, what the workaround is, what
  we expect and when. `message` stays the banner summary.
- Make the banner body itself a link to `/notices/<id>`, not just the small
  "Past notices" link at the end.
- Keep `link_url` for what it was for: a genuinely external target, a docs page
  or a ticket. It is not the detail view and should not become it.

**Add a `NoticeUpdate` child model rather than letting staff edit `detail` in
place.** Incident comms are a timeline — "14:20 investigating", "15:05
mitigated", "16:10 resolved" — and the useful artefact afterwards is that
sequence, not a final paragraph that overwrote its own history. It also gives
the history page a reason to exist, and gives each follow-up email something
specific to say.

While in here, fix the discoverability defect: `/notices` is linked *only* from
inside the banner, on the first live notice. With nothing live there is no
route to it from any menu, and dismissing the last notice takes the link away
too. It needs a permanent nav entry.

## 2. Campaigns — the decision that matters

The important call is not the UI. It is that **service mail and commercial mail
must not share a sending domain or a suppression list.**

| | Maintenance, incidents, deprecations, security advisories | Product updates, newsletters |
|---|---|---|
| Nature | Service / transactional | Commercial |
| Consent | Not required — it concerns a service they bought | Required |
| Unsubscribe | Must NOT be suppressible | Must work, and be honoured |
| Domain | `notification.citemed.com` (warmed, SPF/DKIM/DMARC verified) | its own |

If both go out over one domain and one suppression list, then a customer who
unsubscribes from a product newsletter silently stops receiving incident email.
That is the exact failure EC-SOP-07 §5.2 exists to prevent, and it would be
invisible until it mattered. This is also what the estate already decided for
DeftMarketing: its own Mailgun domain *and* a separate named Django backend.

So, split by the nature of the message rather than by which repo is convenient:

- **Service broadcasts build here, in deft-desk.** This repo already holds the
  audience (`Company`, `PortalUser`, `access_enabled`), the tenancy rules, the
  branded template, and now the notice model these grow out of. A maintenance
  window is a `SiteNotice` that also goes out by email — the same object, one
  composer, two channels.
- **True marketing newsletters go to DeftMarketing** (`deft-ops/server/marketing/`),
  which owns consent, unsubscribe and public pages, and gets its own domain.
  deft-desk exposes the audience; it does not grow a second consent system.

"Product updates" straddles this. A release note about a feature a paying
customer already has is service-adjacent; a "here's what's new, come buy the
new module" is marketing. **Suggest routing product updates through the service
path only when they are genuinely operational** (a change that affects how the
product behaves), and through DeftMarketing otherwise.

### Shape, if we build the service half here

The precedents are already in the repo and should be reused rather than
reinvented:

- **`ShareNotice` is the model to copy.** One row per (push, person), recording
  who we told and whether they ever opened it, with a reminder cadence and a
  per-person daily ceiling. A campaign wants exactly this: a `Campaign` plus a
  `CampaignRecipient` per person, which gives delivery status, open tracking,
  "12 of 40 opened", and resend-to-unopened for free. `ShareNotice`'s comments
  on rate limiting are worth reading before setting any cadence — they were
  written after a real case that produced nine emails to one person.
- **Fan out on Celery, never in the request.** Every send in the portal today
  is synchronous and best-effort, which is right for one email after an upload
  and completely wrong for one broadcast to every customer. `celery` and
  `django-celery-beat` are already in `requirements.txt` and configured.
- **Reuse the send-and-record-together rule** from `file_notify.send_share_email`:
  check the limit, send, and record as one step. Splitting them is how a
  ceiling stops existing.
- **Record delivery per recipient** the way `TicketMessage` does, and reconcile
  it with `poll_mailgun_events`. Without this a campaign is unmeasurable, which
  is the state notices are in now.

### 3. The template

`portal/templates/emails/notification.html` is the branded shell every
notification already uses — table-based, email-client-safe, Inter, the CiteMed
mark, a bulletproof CTA. It takes `heading`, `body`, `note`, `cta_label`,
`cta_url`. Campaigns should use it, with two changes:

- **`body` is a single paragraph.** A campaign needs several, and usually a
  bullet list. Add a `campaign.html` that reuses the same visual shell but
  takes a block of sanitised rich content instead of one string.
- **There is no unsubscribe block.** Correct for service mail; required the
  moment anything commercial goes out. Add it as a footer slot that the
  commercial path fills and the service path replaces with a plain "you are
  receiving this because your organisation uses CiteMed" line.

## Open questions

1. **Do product updates go through the service path or DeftMarketing?** This is
   the fork above and it decides which repo the composer lives in. Everything
   else follows from it.
2. **Who is the "designated account contact" in §5.2?** There is no such field.
   Today the closest thing is every `access_enabled` user at a company, which
   is what `file_notify._company_emails` uses. Either that is the answer, or
   `Company` needs a contact role — and the SOP's wording suggests the latter.
3. **Does a notice email go to a company's users, or to one contact?** Follows
   from (2).

## Before writing any migration

The next number here is **0036**, and PR #58 is already renumbering onto 0036.
Whichever lands second has to move. Check before generating.

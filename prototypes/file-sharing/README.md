# File-sharing prototypes

Two standalone HTML prototypes (no build step, no backend) for adding customer
file sharing to the CiteMed Support Portal. Open them directly in a browser.

## Stage 1 — MVP (`stage1-mvp.html`)

Bare-bones, ship-first scope:

- Drag-drop or click-to-browse upload (multiple files)
- File list: icon, name, size, uploaded date
- Inline rename (click rename → edit → Enter to save / Esc to cancel)
- Delete with confirm modal
- Download (stub)
- Client-side search
- Empty state

Files are a single flat list scoped to the logged-in customer org.

## Stage 2 — Requests / Groups (`stage2-requests.html`)

Stage 1 inside flat *buckets* — explicitly **not** nested folders.
Two kinds of buckets:

- **Requests** — created by a CSM on behalf of the customer, with a title,
  description ("what we need from you"), optional due date, and status
  (`open` / `partial` / `complete`).
- **General uploads** — customer's own bucket for anything not tied to a
  specific ask.

The role toggle in the top-right swaps between the **Customer view** (the
default — uploads, renames, deletes, sees the request description) and the
**CSM view** (creates / edits requests, downloads files, no upload affordance).
That toggle is a prototype-only convenience; in real life the same UI is
gated by `PortalUser` role.

### Things the devs should notice

- No folder tree, no nesting. Buckets are flat — a request *is* the grouping.
- A file belongs to exactly one bucket. Moving between buckets is out of scope
  for v1 of Stage 2 (add later if it comes up).
- Due-date pills color-code: red overdue, amber within 3 days, neutral otherwise.
- The CSM "New request" button lives in the sidebar; "Edit request" lives on
  the detail header. Both should require the CSM role server-side.
- File metadata stays minimal: name, size, uploaded date, uploader. No tags,
  no comments, no versioning in v1.

## Stage 3 — CiteMed Admin view (`stage3-admin.html`)

Internal-facing reuse of the same chassis for our team.

**V1** (default):

- Company switcher at the top — searchable, shows tier + file/open-request counts.
- Same sidebar pattern: Requests sent to the selected company + their general
  uploads bucket. Same detail pane.
- Stat strip (total files, open requests) for the active company.
- Read-only file list with **Download** and **Download all** — no upload, no rename,
  no delete from the admin side in V1 (audit trail simplicity).

**V2** (toggle the V1/V2 pill in the top-right):

- Per-file **review status** — Pending → In review → Approved / Needs revision.
  Inline pill with a dropdown to change state; filter bar to slice the list.
- Per-file **notes** drawer — internal review comments visible to the customer
  when the file is `review` or `revision` (so they know what to fix).
- Per-request **required-documents checklist** — CSM lists what they expect,
  then maps incoming files to checklist slots. Progress bar reflects completion.
- Awaiting-review / Approved counters added to the stat strip.

V1 ships first. V2 layers on without disturbing the V1 surface — same routes,
same components, additional columns + a checklist card above the file list.

### Suggested data model (for backend planning)

```
Bucket
  id, customer_org_id, kind ('request' | 'general'),
  title, description,
  requested_by_user_id (null for 'general'),
  due_at (null), status ('open' | 'partial' | 'complete' | 'general'),
  created_at, updated_at

File
  id, bucket_id, uploader_user_id,
  original_name, storage_key, size_bytes, mime_type,
  uploaded_at, deleted_at (soft-delete)

# V2 additions
File
  + review_status ('pending' | 'review' | 'approved' | 'revision')
  + review_notes (text, visible to customer when status in review/revision)
  + reviewed_by_user_id, reviewed_at

ChecklistItem
  id, bucket_id, text, position,
  linked_file_id (nullable — the file that satisfied this slot),
  created_by_user_id, created_at
```

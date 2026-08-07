# Document folders prototype

One standalone HTML prototype (no build step, no backend) for issue #41 — giving
customers real folder structure for the documents they upload. Open
`folders.html` directly in a browser.

This revisits a decision the earlier `prototypes/file-sharing` mockups made
deliberately: *"No folder tree, no nesting. Buckets are flat — a request is the
grouping."* That held for v1 and no longer does, because everything a customer
uploads lands in one undifferentiated "General uploads" pile.

The role toggle top-right swaps between the **Customer** and **Agent** views.
Prototype convenience only; in real life it's the `PortalUser` role.

## What it demonstrates

- A **nested folder tree** the customer creates and owns, with expand/collapse,
  per-folder counts, and a dot marking folders containing new uploads
- **New subfolder** from wherever you're standing — the modal states which
  parent it lands in
- **Moving files** two ways: multi-select → *Move…*, or drag a file onto a
  folder in the tree
- **Requests pinned above folders**, visually distinct, not part of the tree
- Agent view: a **company switcher**, and a **flat view** toggle that ignores
  folders and shows every file with a Folder column

## The decisions it's there to settle

**1. Requests are not folders.** They're pinned above the tree as a separate,
flat concept. A CiteMed agent asking for something and a customer filing their
own documents are different acts; nesting one inside the other means a customer
could bury a request three levels deep, or delete a folder and take the request
with it. Moving a file *out* of a request detaches it from that request — the
move modal says so.

**2. Adjacency list, not materialised path.** Folders carry `parent` (null =
top level). It's the smallest change to the existing `Bucket` model, and depth
here is single digits — a path column earns its keep at thousands of nodes and
deep queries, which this isn't. Revisit if "search everything under X" gets slow.

**3. The agent needs flat, not the tree.** Best guess going in, and the toggle
is there to check it: an agent asking *"what did they send me?"* wants one list
sorted by date with a Folder column, not to click through someone else's
structure. The tree is for the person who built it. Try both before deciding
whether the agent side needs the tree at all.

**4. "General uploads" stays.** It's the system folder that always exists, so
there's a valid destination before a customer organises anything, and so the
existing `get_general_bucket()` behaviour survives.

## Things the devs should notice

- A file belongs to **exactly one** folder. No copies, no symlinks.
- Deleting a folder that still contains files is **not** modelled here — decide
  between blocking it, cascading, or re-homing to General uploads. Cascading is
  the dangerous one given files are customer documents.
- Re-parenting is where tenant isolation can break: a move must validate that
  the target folder belongs to the **same company**, or a file could be
  re-homed across customers. `SharedFile.for_user` scopes by company today and
  would still pass, since the file's own `company` wouldn't change — which is
  exactly why the check has to be explicit on the folder rather than inferred.
- Folder names are not unique. Two "Clinical data" folders under different
  parents are fine and the breadcrumb disambiguates.
- The new-upload dot is per-folder and rolls up through parents. It needs a
  per-user read model like `TicketRead`, not a boolean on the file, or it'll
  clear for everyone the moment one person looks.
- Counts in the tree are recursive; counts in the header separate "here" from
  "including subfolders". Both matter and they're easy to conflate.
- Nothing here addresses the upload-notification bug in #41 — that fires
  server-side and is independent of this UI.

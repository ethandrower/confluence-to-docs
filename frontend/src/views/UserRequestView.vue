<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="wrap">
        <p v-if="store.loading && !store.loaded" class="state">Loading…</p>

        <!-- Nothing sent yet. Said plainly rather than left as a blank page,
             which reads as a failure to load. -->
        <div v-else-if="!store.request" class="state">
          <h1 class="title">User setup</h1>
          <p class="lede">
            There is no user setup form open for your account right now. Your
            CiteMed contact will send one when it is time to configure your team.
          </p>
        </div>

        <template v-else>
          <header class="head">
            <h1 class="title">Set up your team</h1>
            <p class="lede">
              Tell us who needs access and what each person should be able to
              reach. We will create the accounts and send everyone their own
              sign-in link.
            </p>
            <p v-if="store.request.note" class="note">{{ store.request.note }}</p>
          </header>

          <!-- Counts. `added` and `invited` are read from timestamps the form
               cannot write — see the status column note below. -->
          <div class="counts">
            <span class="count"><strong>{{ store.counts.total }}</strong> {{ store.counts.total === 1 ? 'person' : 'people' }}</span>
            <span class="count count--muted"><strong>{{ store.counts.added }}</strong> set up</span>
            <span class="count count--muted"><strong>{{ store.counts.invited }}</strong> invited</span>
            <span v-if="store.counts.unassigned" class="count count--warn">
              <strong>{{ store.counts.unassigned }}</strong> with no module yet
            </span>
          </div>

          <p v-if="!store.editable" class="banner banner--done">
            Thanks — this has been sent to CiteMed. Contact your CiteMed
            representative if something needs to change.
          </p>

          <p v-if="error" class="banner banner--error">{{ error }}</p>

          <!-- ── Import ─────────────────────────────────────────────────── -->
          <section v-if="store.editable" class="panel">
            <h2 class="panel-title">Have a list already?</h2>
            <p class="panel-lede">
              Upload a spreadsheet instead of typing everyone in. We will show
              you what we read before anything is saved.
            </p>
            <div class="panel-actions">
              <a class="btn btn--ghost" href="/api/roster/template.csv" download>
                Download the template
              </a>
              <label class="btn btn--ghost">
                {{ store.importing ? 'Reading…' : 'Choose a file' }}
                <input
                  ref="fileInput"
                  type="file"
                  accept=".csv,.xlsx,.xlsm,text/csv"
                  class="sr-only"
                  :disabled="store.importing"
                  @change="onFile"
                />
              </label>
              <span class="hint">CSV or Excel</span>
            </div>
          </section>

          <!-- Confirmation step. The whole point of the two-phase import: the
               customer sees what each column was understood as, and can correct
               it, before a single row is written. -->
          <section v-if="review" class="panel panel--review">
            <h2 class="panel-title">Check this looks right</h2>
            <p class="panel-lede">
              {{ review.filename }} — {{ review.row_count }}
              {{ review.row_count === 1 ? 'row' : 'rows' }}. Nothing has been
              saved yet.
            </p>

            <div class="map">
              <div v-for="(header, i) in review.headers" :key="i" class="map-col">
                <span class="map-head" :title="header">{{ header || '(no heading)' }}</span>
                <select
                  class="map-select"
                  :value="mapping[String(i)] || ''"
                  @change="onRemap(String(i), $event.target.value)"
                >
                  <option value="">Do not import</option>
                  <option
                    v-for="option in review.field_options"
                    :key="option.key"
                    :value="option.key"
                  >{{ option.label }}</option>
                </select>
              </div>
            </div>

            <p v-if="!mappedFields.includes('email')" class="banner banner--error">
              Point one column at <strong>Email</strong> — without it there is
              nothing to import people under.
            </p>

            <div class="table-scroll">
              <table class="table">
                <thead>
                  <tr>
                    <th>Row</th><th>Name</th><th>Email</th>
                    <th>Modules</th><th>Role</th><th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in review.preview"
                    :key="row.line"
                    :class="{ 'row--skip': !row.importable }"
                  >
                    <td class="num">{{ row.line }}</td>
                    <td>{{ [row.first_name, row.last_name].filter(Boolean).join(' ') || '—' }}</td>
                    <td>{{ row.email || '—' }}</td>
                    <td>{{ labelsFor(row.modules) || '—' }}</td>
                    <td>{{ roleLabel(row.role_type) }}</td>
                    <td class="problems">
                      <span v-if="!row.problems.length" class="ok">Looks fine</span>
                      <span
                        v-for="(problem, i) in row.problems"
                        :key="i"
                        class="problem"
                      >{{ problem.message }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="panel-actions">
              <button
                class="btn btn--primary"
                :disabled="!mappedFields.includes('email') || busy"
                @click="confirmImport"
              >Import {{ importableCount }} {{ importableCount === 1 ? 'person' : 'people' }}</button>
              <button class="btn btn--ghost" :disabled="busy" @click="discard">Cancel</button>
            </div>
          </section>

          <!-- Applied by the cron runner, not by the request that confirmed it,
               so this is what the customer watches while that happens. -->
          <section v-if="store.importRunning" class="panel panel--busy">
            <h2 class="panel-title">Importing…</h2>
            <p class="panel-lede">
              Your list is being added. This usually takes under a minute — you
              can keep working, and the table will fill in.
            </p>
          </section>

          <section
            v-else-if="store.pendingImport?.state === 'done'"
            class="panel panel--done"
          >
            <h2 class="panel-title">Import finished</h2>
            <p class="panel-lede">
              {{ store.pendingImport.created_count }} added,
              {{ store.pendingImport.updated_count }} updated<span
                v-if="store.pendingImport.skipped_count"
              >, {{ store.pendingImport.skipped_count }} skipped</span>.
            </p>
            <ul v-if="store.pendingImport.problems.length" class="problem-list">
              <li v-for="(problem, i) in store.pendingImport.problems.slice(0, 10)" :key="i">
                Row {{ problem.row }}: {{ problem.message }}
              </li>
            </ul>
            <div class="panel-actions">
              <button class="btn btn--ghost" @click="store.pendingImport = null">Dismiss</button>
            </div>
          </section>

          <section v-else-if="store.pendingImport?.state === 'failed'" class="panel panel--error">
            <h2 class="panel-title">That import did not finish</h2>
            <p class="panel-lede">
              Nothing was saved. Try uploading the file again, or add people by
              hand below.
            </p>
          </section>

          <!-- ── The roster ─────────────────────────────────────────────── -->
          <section class="panel">
            <h2 class="panel-title">Your people</h2>

            <p v-if="!store.users.length" class="empty">
              Nobody yet. Add your first person below.
            </p>

            <div v-else class="table-scroll">
              <table class="table">
                <thead>
                  <tr>
                    <th>Name</th><th>Email</th><th>Modules</th>
                    <th>Access</th><th>Status</th><th v-if="store.editable"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="person in store.users" :key="person.id">
                    <td>{{ displayName(person) }}</td>
                    <td class="mono">{{ person.email }}</td>
                    <td>
                      <div v-if="store.editable" class="chips">
                        <label
                          v-for="option in store.moduleOptions"
                          :key="option.key"
                          class="chip"
                          :class="{ 'chip--on': person.modules.includes(option.key) }"
                        >
                          <input
                            type="checkbox"
                            class="sr-only"
                            :checked="person.modules.includes(option.key)"
                            @change="toggleFor(person, option.key)"
                          />
                          {{ option.label }}
                        </label>
                      </div>
                      <span v-else>{{ labelsFor(person.modules) || '—' }}</span>
                    </td>
                    <td>
                      <select
                        v-if="store.editable"
                        class="select"
                        :value="person.role_type"
                        @change="setRole(person, $event.target.value)"
                      >
                        <option v-for="r in store.roleOptions" :key="r.key" :value="r.key">
                          {{ r.label }}
                        </option>
                      </select>
                      <span v-else>{{ roleLabel(person.role_type) }}</span>
                    </td>

                    <!-- Read-only, always. These two come back from what we
                         actually did; there is no control here that sets them
                         and no request path that would accept them. -->
                    <td>
                      <span class="pill" :class="`pill--${statusOf(person)}`">
                        {{ STATUS_LABELS[statusOf(person)] }}
                      </span>
                      <span v-if="person.status_note" class="status-note" :title="person.status_note">
                        note
                      </span>
                    </td>

                    <td v-if="store.editable" class="right">
                      <button
                        class="link-btn"
                        :disabled="Boolean(person.added_at)"
                        :title="person.added_at
                          ? 'Already set up — contact CiteMed to remove access'
                          : 'Remove'"
                        @click="remove(person)"
                      >Remove</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Add a row. Kept as its own form rather than an editable blank
                 table row so an incomplete entry cannot be mistaken for
                 somebody who is on the list. -->
            <form v-if="store.editable" class="add" @submit.prevent="addRow">
              <div class="add-grid">
                <input v-model="draft.first_name" class="input" placeholder="First name" />
                <input v-model="draft.last_name" class="input" placeholder="Last name" />
                <input
                  v-model="draft.email"
                  class="input"
                  :class="{ 'input--bad': draftErrors.email && draftTouched }"
                  type="email"
                  placeholder="Email address"
                  @blur="draftTouched = true"
                />
                <select v-model="draft.role_type" class="select">
                  <option v-for="r in store.roleOptions" :key="r.key" :value="r.key">
                    {{ r.label }}
                  </option>
                </select>
              </div>
              <div class="chips chips--add">
                <label
                  v-for="option in store.moduleOptions"
                  :key="option.key"
                  class="chip"
                  :class="{ 'chip--on': draft.modules.includes(option.key) }"
                >
                  <input
                    type="checkbox"
                    class="sr-only"
                    :checked="draft.modules.includes(option.key)"
                    @change="draft.modules = toggleModule(draft.modules, option.key)"
                  />
                  {{ option.label }}
                </label>
              </div>
              <p v-if="draftTouched && draftErrors.email" class="field-error">
                {{ draftErrors.email }}
              </p>
              <button class="btn btn--primary" type="submit" :disabled="busy || !draftValid">
                Add person
              </button>
            </form>
          </section>

          <!-- ── Module expanders ───────────────────────────────────────── -->
          <section v-if="store.users.length" class="panel">
            <h2 class="panel-title">By module</h2>
            <p class="panel-lede">
              Who you have put on each one. A module with nobody in it is worth
              a second look before you send this.
            </p>

            <details v-for="group in store.byModule" :key="group.key" class="exp">
              <summary class="exp-head">
                <span class="exp-name">{{ group.label }}</span>
                <span class="exp-count" :class="{ 'exp-count--zero': !group.users.length }">
                  {{ group.users.length }}
                </span>
              </summary>
              <ul v-if="group.users.length" class="exp-list">
                <li v-for="person in group.users" :key="person.id">
                  {{ displayName(person) }}
                  <span class="exp-role">{{ roleLabel(person.role_type) }}</span>
                </li>
              </ul>
              <p v-else class="exp-empty">Nobody has been given {{ group.label }}.</p>
            </details>

            <details v-if="store.unassigned.length" class="exp exp--warn">
              <summary class="exp-head">
                <span class="exp-name">No module yet</span>
                <span class="exp-count exp-count--warn">{{ store.unassigned.length }}</span>
              </summary>
              <ul class="exp-list">
                <li v-for="person in store.unassigned" :key="person.id">
                  {{ displayName(person) }}
                </li>
              </ul>
              <p class="exp-empty">
                These people will get portal access — tickets, files and
                documentation — but no product modules.
              </p>
            </details>
          </section>

          <!-- ── Submit ─────────────────────────────────────────────────── -->
          <section v-if="store.editable" class="submit">
            <ul v-if="blockers.length" class="blockers">
              <li v-for="(b, i) in blockers" :key="i">{{ b }}</li>
            </ul>
            <button
              class="btn btn--primary btn--lg"
              :disabled="blockers.length > 0 || busy"
              @click="onSubmit"
            >Send to CiteMed</button>
            <p class="submit-hint">
              You can still ask us to reopen this afterwards.
            </p>
          </section>
        </template>
      </div>
    </template>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import { useRosterStore } from '@/stores/roster.js'
import {
  blankRow, toggleModule, rowErrors, displayName, statusOf, submitBlockers,
} from '@/lib/roster.js'

const STATUS_LABELS = {
  pending: 'Waiting on us',
  added: 'Set up',
  invited: 'Invited',
}

const store = useRosterStore()
const error = ref('')
const busy = ref(false)
const fileInput = ref(null)
const draft = reactive(blankRow())
const draftTouched = ref(false)

const review = computed(() =>
  store.pendingImport?.state === 'pending_review' ? store.pendingImport : null)

const mapping = computed(() => review.value?.mapping || {})
const mappedFields = computed(() => Object.values(mapping.value))
const importableCount = computed(() =>
  (review.value?.preview || []).filter((r) => r.importable).length)

const draftErrors = computed(() =>
  rowErrors(draft, { existingEmails: store.users.map((u) => u.email) }))
const draftValid = computed(() => Object.keys(draftErrors.value).length === 0)

const blockers = computed(() =>
  submitBlockers(store.users, { importRunning: store.importRunning }))

function labelsFor(keys) {
  const byKey = Object.fromEntries(store.moduleOptions.map((m) => [m.key, m.label]))
  return (keys || []).map((k) => byKey[k] || k).join(', ')
}

function roleLabel(key) {
  return store.roleOptions.find((r) => r.key === key)?.label || key
}

async function guard(fn) {
  busy.value = true
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = e.message || 'Something went wrong.'
  } finally {
    busy.value = false
  }
}

async function addRow() {
  draftTouched.value = true
  if (!draftValid.value) return
  await guard(async () => {
    await store.addUser({ ...draft })
    Object.assign(draft, blankRow())
    draftTouched.value = false
  })
}

function toggleFor(person, key) {
  guard(() => store.updateUser(person.id, {
    modules: toggleModule(person.modules, key),
  }))
}

function setRole(person, role) {
  guard(() => store.updateUser(person.id, { role_type: role }))
}

function remove(person) {
  guard(() => store.removeUser(person.id))
}

function onFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  guard(() => store.uploadFile(file))
  // Cleared so choosing the same file twice still fires a change event.
  event.target.value = ''
}

function onRemap(index, field) {
  const next = { ...mapping.value }
  if (field) next[index] = field
  else delete next[index]
  guard(() => store.remap(next))
}

function confirmImport() {
  guard(async () => {
    await store.confirmImport(mapping.value)
    await store.watchImport()
  })
}

function discard() {
  guard(() => store.discardImport())
}

function onSubmit() {
  guard(() => store.submit())
}

onMounted(() => store.load())
</script>

<style scoped>
.wrap { max-width: 68rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
.state { padding: 2rem 0; color: #475569; }
.title { margin: 0 0 .5rem; font-size: 1.6rem; font-weight: 700; color: #0f172a; letter-spacing: -.02em; }
.lede { margin: 0; color: #475569; line-height: 1.6; max-width: 46rem; }
.note { margin: 1rem 0 0; padding: .75rem 1rem; background: #f1f5f9; border-left: 3px solid #2d5296; border-radius: 0 6px 6px 0; color: #334155; }
.head { margin-bottom: 1.25rem; }

.counts { display: flex; flex-wrap: wrap; gap: 1.25rem; padding: .75rem 0 1.25rem; border-bottom: 1px solid #e2e8f0; margin-bottom: 1.5rem; }
.count { font-size: .875rem; color: #0f172a; }
.count strong { font-size: 1.05rem; }
.count--muted { color: #64748b; }
.count--warn { color: #b45309; }

.banner { margin: 0 0 1rem; padding: .75rem 1rem; border-radius: 8px; font-size: .9rem; }
.banner--done { background: #ecfdf5; color: #065f46; }
.banner--error { background: #fef2f2; color: #991b1b; }

.panel { border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; background: #fff; }
.panel--review { border-color: #2d5296; }
.panel--busy { background: #f8fafc; }
.panel--done { border-color: #a7f3d0; }
.panel--error { border-color: #fecaca; }
.panel-title { margin: 0 0 .35rem; font-size: 1.05rem; font-weight: 650; color: #0f172a; }
.panel-lede { margin: 0 0 1rem; color: #64748b; font-size: .9rem; line-height: 1.55; }
.panel-actions { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; }
.hint { font-size: .8rem; color: #94a3b8; }

.btn { display: inline-flex; align-items: center; gap: .4rem; padding: .5rem .9rem; border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; color: #0f172a; font-size: .875rem; font-weight: 550; cursor: pointer; text-decoration: none; }
.btn:hover { background: #f8fafc; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--primary { background: #2d5296; border-color: #2d5296; color: #fff; }
.btn--primary:hover:not(:disabled) { background: #24427a; }
.btn--ghost { background: #fff; }
.btn--lg { padding: .65rem 1.4rem; font-size: .95rem; }

.map { display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: 1rem; }
.map-col { display: flex; flex-direction: column; gap: .25rem; min-width: 10rem; }
.map-head { font-size: .75rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .04em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.map-select, .select { padding: .35rem .5rem; border: 1px solid #cbd5e1; border-radius: 6px; font-size: .85rem; background: #fff; color: #0f172a; }

.table-scroll { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: .875rem; }
.table th { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #e2e8f0; color: #64748b; font-weight: 600; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
.table td { padding: .55rem .6rem; border-bottom: 1px solid #f1f5f9; vertical-align: middle; color: #0f172a; }
.row--skip { background: #fffbeb; color: #92400e; }
.num { color: #94a3b8; font-variant-numeric: tabular-nums; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .82rem; }
.right { text-align: right; }
.problems { display: flex; flex-direction: column; gap: .2rem; }
.problem { color: #b45309; font-size: .8rem; }
.ok { color: #94a3b8; font-size: .8rem; }

.chips { display: flex; flex-wrap: wrap; gap: .3rem; }
.chips--add { margin: .6rem 0; }
.chip { display: inline-flex; align-items: center; padding: .2rem .55rem; border: 1px solid #cbd5e1; border-radius: 999px; font-size: .78rem; cursor: pointer; color: #475569; background: #fff; user-select: none; }
.chip--on { background: #2d5296; border-color: #2d5296; color: #fff; }

.pill { display: inline-block; padding: .15rem .5rem; border-radius: 999px; font-size: .75rem; font-weight: 600; }
.pill--pending { background: #f1f5f9; color: #64748b; }
.pill--added { background: #eff6ff; color: #1d4ed8; }
.pill--invited { background: #ecfdf5; color: #047857; }
.status-note { margin-left: .35rem; font-size: .7rem; color: #94a3b8; border-bottom: 1px dotted #cbd5e1; cursor: help; }

.link-btn { background: none; border: 0; color: #b91c1c; font-size: .82rem; cursor: pointer; padding: 0; }
.link-btn:disabled { color: #cbd5e1; cursor: not-allowed; }

.empty { color: #94a3b8; padding: 1rem 0; }
.add { margin-top: 1rem; padding-top: 1rem; border-top: 1px dashed #e2e8f0; }
.add-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: .5rem; }
.input { padding: .45rem .6rem; border: 1px solid #cbd5e1; border-radius: 6px; font-size: .875rem; color: #0f172a; }
.input--bad { border-color: #f87171; }
.field-error { color: #b91c1c; font-size: .8rem; margin: .25rem 0 .5rem; }

.exp { border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: .5rem; }
.exp--warn { border-color: #fcd34d; }
.exp-head { display: flex; align-items: center; justify-content: space-between; padding: .6rem .85rem; cursor: pointer; font-size: .9rem; }
.exp-name { font-weight: 550; color: #0f172a; }
.exp-count { min-width: 1.6rem; text-align: center; padding: .1rem .45rem; background: #eff6ff; color: #1d4ed8; border-radius: 999px; font-size: .78rem; font-weight: 600; }
.exp-count--zero { background: #f1f5f9; color: #94a3b8; }
.exp-count--warn { background: #fef3c7; color: #92400e; }
.exp-list { margin: 0; padding: 0 .85rem .75rem 1.75rem; color: #334155; font-size: .875rem; }
.exp-list li { padding: .15rem 0; }
.exp-role { color: #94a3b8; font-size: .8rem; margin-left: .4rem; }
.exp-empty { margin: 0; padding: 0 .85rem .75rem; color: #94a3b8; font-size: .82rem; }

.problem-list { margin: 0 0 1rem; padding-left: 1.25rem; color: #b45309; font-size: .85rem; }
.submit { padding-top: .5rem; }
.blockers { margin: 0 0 .75rem; padding-left: 1.25rem; color: #b45309; font-size: .875rem; }
.submit-hint { margin: .5rem 0 0; color: #94a3b8; font-size: .8rem; }

.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
</style>

<template>
  <li class="fn">
    <div
      class="fn-row"
      :class="{ 'is-active': node.id === activeId, 'is-drop': dropping }"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      @dragover.prevent="onDragOver"
      @dragleave="dropping = false"
      @drop.prevent="onDrop"
    >
      <button
        class="fn-twisty"
        :class="{ 'is-open': open, 'is-leaf': !node.children.length }"
        :aria-label="open ? 'Collapse' : 'Expand'"
        :disabled="!node.children.length"
        @click.stop="open = !open"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
      </button>

      <button class="fn-btn" :draggable="!readOnly" @click="$emit('select', node.id)" @dragstart="onFolderDragStart">
        <svg class="fn-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>
        <span class="fn-title" :title="node.title">{{ node.title }}</span>
        <!-- Deep counts: at a COLLAPSED node the number that matters is
             everything inside, not just what sits at this exact level —
             otherwise a folder full of new files reads as empty. -->
        <span v-if="node.deepUnseen" class="fn-newcount" :title="`${node.deepUnseen} not yet looked at`">
          {{ node.deepUnseen }} new
        </span>
        <span v-if="node.deepCount" class="fn-count">{{ node.deepCount }}</span>
      </button>

      <!-- Subfolders get made where the structure is, not from a button in
           the detail pane on the other side of the screen. -->
      <button v-if="!readOnly" class="fn-add" title="New subfolder"
              :aria-label="`New folder inside ${node.title}`"
              @click.stop="$emit('add-child', node.id)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
      </button>
    </div>

    <ul v-if="open && (node.children.length || creatingIn === node.id)" class="fn-children">
      <li v-if="creatingIn === node.id" class="fn-new" :style="{ paddingLeft: 22 + depth * 14 + 'px' }">
        <input
          ref="newInput"
          v-model="draft"
          class="fn-new-input"
          placeholder="Folder name"
          @keydown.enter="submit"
          @keydown.esc="$emit('create-cancel')"
        />
        <div class="fn-new-actions">
          <button class="fn-new-btn" @click="submit">Create</button>
          <button class="fn-new-btn" @click="$emit('create-cancel')">Cancel</button>
        </div>
      </li>

      <FolderNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :active-id="activeId"
        :depth="depth + 1"
        :creating-in="creatingIn"
        :read-only="readOnly"
        @select="$emit('select', $event)"
        @drop-files="$emit('drop-files', $event)"
        @move-folder="$emit('move-folder', $event)"
        @add-child="$emit('add-child', $event)"
        @create-submit="$emit('create-submit', $event)"
        @create-cancel="$emit('create-cancel')"
      />
    </ul>
  </li>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  // A node from buildFolderTree(): carries children + ownCount/deepCount/
  // deepUnseen. Presentational on purpose — this component reads no store, so
  // the customer page and the agent's client view can both render it from
  // their own data.
  node: { type: Object, required: true },
  activeId: { type: [Number, null], default: null },
  depth: { type: Number, default: 0 },
  // id of the folder currently being added to, or undefined when idle.
  creatingIn: { type: [Number, null, undefined], default: undefined },
  // Agents don't reorganise the customer's filing.
  readOnly: { type: Boolean, default: false },
})
const emit = defineEmits([
  'select', 'drop-files', 'move-folder', 'add-child', 'create-submit', 'create-cancel',
])

// Open by default so a customer sees their structure rather than a row of
// closed boxes; they can collapse what they don't want.
const open = ref(true)
const dropping = ref(false)
const draft = ref('')
const newInput = ref(null)

// A collapsed folder must open when you add to it, or the new input renders
// inside a hidden subtree and the click appears to do nothing.
watch(() => props.creatingIn, (v) => {
  if (v === props.node.id) {
    open.value = true
    draft.value = ''
    nextTick(() => newInput.value?.focus())
  }
})

function submit() {
  const title = draft.value.trim()
  if (!title) return emit('create-cancel')
  emit('create-submit', { title, parentId: props.node.id })
}

function onDragOver(e) {
  if (props.readOnly) return
  dropping.value = true
  e.dataTransfer.dropEffect = 'move'
}

function onFolderDragStart(e) {
  if (props.readOnly) return
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('application/x-folder-id', String(props.node.id))
}

function onDrop(e) {
  if (props.readOnly) return
  dropping.value = false
  const folderId = e.dataTransfer.getData('application/x-folder-id')
  if (folderId) {
    // Dropping a folder on itself is a no-op, not an error worth showing.
    if (Number(folderId) !== props.node.id) {
      emit('move-folder', { id: Number(folderId), parentId: props.node.id })
    }
    return
  }
  const raw = e.dataTransfer.getData('application/x-file-ids')
  if (raw) emit('drop-files', { ids: JSON.parse(raw), bucketId: props.node.id })
}
</script>

<style scoped>
.fn { list-style: none; }
.fn-children { list-style: none; margin: 0; padding: 0; }

.fn-row {
  display: flex; align-items: center; gap: 2px;
  border-radius: 7px; padding-right: 6px;
}
.fn-row.is-active { background: var(--accent); }
.fn-row:hover { background: color-mix(in srgb, var(--accent) 60%, transparent); }
/* The drop target has to be unmistakable — a mis-drop silently files a
   document in the wrong place and the customer won't know where it went. */
.fn-row.is-drop {
  background: color-mix(in srgb, var(--primary) 16%, transparent);
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.fn-twisty {
  display: grid; place-items: center;
  width: 18px; height: 26px; flex-shrink: 0;
  border: 0; background: none; cursor: pointer;
  color: var(--muted-foreground);
}
.fn-twisty svg { width: 13px; height: 13px; transition: transform 0.12s ease; }
.fn-twisty.is-open svg { transform: rotate(90deg); }
.fn-twisty.is-leaf { visibility: hidden; cursor: default; }

.fn-btn {
  display: flex; align-items: center; gap: 7px;
  flex: 1; min-width: 0;
  padding: 5px 2px;
  border: 0; background: none; cursor: pointer;
  font-family: var(--font-ui); font-size: 0.83rem;
  color: var(--foreground); text-align: left;
}
.fn-ico { width: 15px; height: 15px; flex-shrink: 0; color: var(--muted-foreground); }
.fn-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fn-count {
  margin-left: auto; flex-shrink: 0;
  font-size: 0.72rem; color: var(--muted-foreground); font-variant-numeric: tabular-nums;
}
/* The one thing an agent is scanning this tree for. Sits before the total so
   "3 new" reads ahead of "12". */
.fn-newcount {
  margin-left: auto; flex-shrink: 0;
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.02em;
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  border-radius: 999px; padding: 1px 7px;
}
.fn-newcount + .fn-count { margin-left: 6px; }

/* Revealed on hover/focus so the tree stays quiet at rest, but always
   reachable by keyboard. */
.fn-add {
  display: grid; place-items: center;
  width: 20px; height: 20px; flex-shrink: 0;
  margin-left: 4px; padding: 0;
  border: 0; border-radius: 5px; background: none; cursor: pointer;
  color: var(--muted-foreground); opacity: 0;
}
.fn-add svg { width: 13px; height: 13px; }
.fn-row:hover .fn-add, .fn-add:focus-visible { opacity: 1; }
.fn-add:hover { background: var(--background); color: var(--foreground); }

.fn-new { list-style: none; padding-right: 6px; padding-top: 3px; }
.fn-new-input {
  width: 100%; height: 26px; padding: 0 7px;
  border: 1px solid var(--primary); border-radius: 6px;
  background: var(--background); color: var(--foreground);
  font-family: var(--font-ui); font-size: 0.8rem;
}
.fn-new-actions { display: flex; gap: 8px; margin: 4px 0 2px; }
.fn-new-btn {
  border: 0; background: none; padding: 0; cursor: pointer;
  font-family: var(--font-ui); font-size: 0.74rem; color: var(--muted-foreground);
}
.fn-new-btn:hover { color: var(--foreground); text-decoration: underline; }
</style>

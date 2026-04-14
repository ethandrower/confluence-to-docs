<template>
  <div ref="contentRef" class="confluence-content" v-html="processedHtml" />
</template>

<script setup>
import { computed, ref, onMounted, watch, nextTick } from 'vue'

const props = defineProps({ html: String })
const contentRef = ref(null)

const processedHtml = computed(() => {
  if (!props.html) return ''
  let h = props.html

  // ── Clean Confluence custom tags ─────────────────────────
  // Emoji
  h = h.replace(/<custom[^>]*data-type="emoji"[^>]*>(:[a-z_]+:)<\/custom>/gi, (_, code) => EMOJI[code] || '')
  // Mentions
  h = h.replace(/<custom[^>]*data-type="mention"[^>]*>[^<]*<\/custom>/gi, '')
  // Placeholders
  h = h.replace(/<custom[^>]*data-type="placeholder"[^>]*>[^<]*<\/custom>/gi, '')
  // Status → badge
  h = h.replace(/<custom[^>]*data-type="status"[^>]*>([^<]*)<\/custom>/gi,
    '<span class="status-badge">$1</span>')
  // Smart links → anchor
  h = h.replace(/<custom[^>]*data-type="smartlink"[^>]*>(https?:\/\/[^<]*)<\/custom>/gi,
    '<a href="$1">$1</a>')
  // Remaining custom tags
  h = h.replace(/<\/?custom[^>]*>/gi, '')

  // ── Fix broken blob images ───────────────────────────────
  h = h.replace(/<img[^>]*src="blob:[^"]*"[^>]*\/?>/gi,
    '<div class="img-placeholder">Image unavailable — requires API token sync</div>')

  // ── Convert standalone pipe tables to HTML ────────────────
  // Some pages have raw markdown pipe tables that were never converted.
  // Detect and convert them before the broken-table fixer runs.
  h = convertStandalonePipeTables(h)

  // ── Fix broken pipe tables ───────────────────────────────
  // The markdown converter often renders only the thead + first row,
  // then dumps remaining rows as raw pipe text inside <p> or loose text.
  // Strategy: use DOM to find tables followed by pipe-text and merge them.
  h = fixBrokenTables(h)

  // ── Wrap tables for scroll ───────────────────────────────
  h = h.replace(/<table/g, '<div class="table-wrap"><table')
  h = h.replace(/<\/table>/g, '</table></div>')

  // ── Heading anchors ──────────────────────────────────────
  h = h.replace(/<(h[2-4])\s+id="([^"]+)">/g,
    '<$1 id="$2" class="group relative"><a href="#$2" class="anchor-link" aria-hidden="true">#</a>')

  // ── Enhance content patterns (DOM-based) ────────────────
  h = enhanceContentPatterns(h)

  return h
})

function enhanceContentPatterns(html) {
  const div = document.createElement('div')
  div.innerHTML = html

  // 1. Convert definition-style paragraphs into styled cards
  //    Pattern: <p><strong>ALL CAPS LABEL.</strong> Body text...</p>
  div.querySelectorAll('p').forEach(p => {
    const strong = p.querySelector('strong:first-child')
    if (!strong) return
    const strongText = strong.textContent.trim()
    // Must be ALL CAPS with a trailing period and have body text after it
    if (!/^[A-Z][A-Z\s,\-&/.0-9]+\.\s*$/.test(strongText + ' ')) return
    const bodyText = p.innerHTML.replace(strong.outerHTML, '').trim()
    if (!bodyText || bodyText.length < 10) return

    p.classList.add('def-entry')
  })

  // 2. Convert lists where every item has <strong>Term</strong> - Description
  //    into rich card lists
  div.querySelectorAll('ul').forEach(ul => {
    const items = [...ul.children]
    if (items.length < 2) return
    const richItems = items.filter(li => {
      const strong = li.querySelector('strong:first-child')
      return strong && li.textContent.length > strong.textContent.length + 5
    })
    // If majority of items have the bold-term pattern, enhance the list
    if (richItems.length >= items.length * 0.6) {
      ul.classList.add('rich-list')
    }
  })

  return div.innerHTML
}

function convertStandalonePipeTables(html) {
  // Match blocks of pipe-delimited lines separated by <br> tags.
  // Pattern: at least 3 consecutive lines starting with | and having 3+ pipes.
  // These are full markdown tables never converted to HTML.
  return html.replace(
    /(?:(?:^|<br\s*\/?>|\n)\s*\|[^\n]*\|[ \t]*(?:<br\s*\/?>|\n)){3,}/gi,
    (match) => {
      const lines = match
        .split(/<br\s*\/?>|\n/)
        .map(l => l.trim())
        .filter(l => l.startsWith('|') && l.endsWith('|') && l.split('|').length >= 3)

      if (lines.length < 3) return match  // Need header + separator + at least 1 row

      // Check for separator row (| --- | --- |)
      const sepIdx = lines.findIndex(l => {
        const cells = l.slice(1, -1).split('|')
        return cells.every(c => /^\s*[-:]+\s*$/.test(c))
      })
      if (sepIdx < 1) return match  // No valid separator found

      const headerLines = lines.slice(0, sepIdx)
      const bodyLines = lines.slice(sepIdx + 1)

      function parseRow(line) {
        return line.slice(1, -1).split('|').map(c => c.trim())
      }

      // Build thead
      let thead = '<thead>'
      for (const hLine of headerLines) {
        const cells = parseRow(hLine)
        thead += '<tr>' + cells.map(c => `<th>${c}</th>`).join('') + '</tr>'
      }
      thead += '</thead>'

      // Build tbody
      let tbody = '<tbody>'
      for (const bLine of bodyLines) {
        if (!bLine.trim()) continue
        const cells = parseRow(bLine)
        tbody += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>'
      }
      tbody += '</tbody>'

      return `<table>${thead}${tbody}</table>`
    }
  )
}

function fixBrokenTables(html) {
  const div = document.createElement('div')
  div.innerHTML = html

  const tables = div.querySelectorAll('table')
  tables.forEach(table => {
    const tbody = table.querySelector('tbody') || table
    const toRemove = []

    // The last <td> in the table may have been truncated.
    // The broken content starts in the next sibling with the remainder of that cell.
    const lastTd = tbody.querySelector('tr:last-child td:last-child')

    let node = table.nextSibling
    while (node) {
      const nextNode = node.nextSibling

      // Skip whitespace text nodes
      if (node.nodeType === 3 && !node.textContent.trim()) {
        node = nextNode
        continue
      }

      const content = node.nodeType === 1 ? node.innerHTML : node.textContent
      if (!content || !/\|/.test(content)) break

      const lines = content.split(/<br\s*\/?>|\n/)
      // Count header columns to detect incomplete rows
      const headerCols = table.querySelectorAll('thead th').length || 0

      let addedRows = false
      let firstLine = true

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue

        const isPipeRow = trimmed.startsWith('|')
        const pipeCount = (trimmed.match(/\|/g) || []).length

        if (firstLine && !isPipeRow && lastTd) {
          // Continuation of last cell — e.g. "Full Stack  |"
          const cellText = trimmed.replace(/\|$/, '').trim()
          if (cellText) lastTd.innerHTML += ' ' + cellText
          firstLine = false
          continue
        }
        firstLine = false

        if (pipeCount < 2) continue

        let raw = trimmed
        if (raw.startsWith('|')) raw = raw.substring(1)
        if (raw.endsWith('|')) raw = raw.slice(0, -1)

        const cells = raw.split('|').map(c => c.trim())
        if (cells.every(c => /^[-:\s]*$/.test(c.replace(/<[^>]+>/g, '')))) continue
        if (cells.length < 2) continue

        const tr = document.createElement('tr')
        cells.forEach(cellHtml => {
          const td = document.createElement('td')
          td.innerHTML = cellHtml
          tr.appendChild(td)
        })

        // If row has fewer cells than header, pad with empty cells
        while (headerCols && tr.children.length < headerCols) {
          tr.appendChild(document.createElement('td'))
        }

        tbody.appendChild(tr)
        addedRows = true
      }

      if (addedRows || toRemove.length === 0) {
        toRemove.push(node)
        node = nextNode
      } else {
        break
      }
    }

    // Count columns from thead to know what a full row looks like
    const headerCols = table.querySelectorAll('thead th').length || 0

    // Scan further orphan <p> tags — may contain:
    // - full pipe rows
    // - partial text (continuation of a cell, like "and/or")
    // - partial pipe rows (fewer cols than header — append to last row's last cell)
    let scan = toRemove.length ? toRemove[toRemove.length - 1].nextSibling : null
    let maxLookahead = 10
    while (scan && maxLookahead-- > 0) {
      const nextScan = scan.nextSibling
      if (scan.nodeType === 3 && !scan.textContent.trim()) { scan = nextScan; continue }
      const tag = scan.nodeName?.toLowerCase()
      if (tag !== 'p') break

      const inner = (scan.innerHTML || scan.textContent || '').trim()
      if (!inner) { scan = nextScan; continue }

      const pipeCount = (inner.match(/\|/g) || []).length

      if (pipeCount >= 2) {
        const lines = inner.split(/<br\s*\/?>|\n/)
        for (const line of lines) {
          const t = line.trim()
          if (!t) continue
          let raw = t
          if (raw.startsWith('|')) raw = raw.substring(1)
          if (raw.endsWith('|')) raw = raw.slice(0, -1)
          const cells = raw.split('|').map(c => c.trim())
          if (cells.every(c => /^[-:\s]*$/.test(c.replace(/<[^>]+>/g, '')))) continue
          if (cells.length < 2) continue

          if (headerCols && cells.length < headerCols / 2) {
            // Way fewer cells than header — this is a continuation, not a new row
            const lastRow = tbody.querySelector('tr:last-child')
            const lastCell = lastRow?.querySelector('td:last-child')
            if (lastCell) lastCell.innerHTML += '<br>' + t.replace(/^\||\|$/g, '').trim()
          } else {
            const tr = document.createElement('tr')
            cells.forEach(ch => { const td = document.createElement('td'); td.innerHTML = ch; tr.appendChild(td) })
            while (headerCols && tr.children.length < headerCols) tr.appendChild(document.createElement('td'))
            tbody.appendChild(tr)
          }
        }
        toRemove.push(scan)
        scan = nextScan
      } else if (pipeCount <= 1) {
        // No pipes or just one — plain text continuation of previous cell
        // e.g. "and/or" between two parts of a cell
        const lastRow = tbody.querySelector('tr:last-child')
        const lastCell = lastRow?.querySelector('td:last-child')
        if (lastCell) {
          lastCell.innerHTML += '<br>' + inner.replace(/\|/g, '').trim()
        }
        toRemove.push(scan)
        scan = nextScan
      } else {
        break
      }
    }

    toRemove.forEach(n => n.parentNode?.removeChild(n))
  })

  return div.innerHTML
}

// ── Post-render: copy buttons, syntax highlight ────────────
function enhance() {
  if (!contentRef.value) return
  const el = contentRef.value

  el.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.copy-btn')) return
    const btn = document.createElement('button')
    btn.className = 'copy-btn'
    btn.setAttribute('aria-label', 'Copy code')
    btn.textContent = 'Copy'
    btn.addEventListener('click', () => {
      const code = pre.querySelector('code')
      navigator.clipboard.writeText(code?.textContent || pre.textContent)
      btn.textContent = 'Copied!'
      btn.classList.add('copied')
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied') }, 1500)
    })
    pre.style.position = 'relative'
    pre.appendChild(btn)
  })

  if (window.Prism) window.Prism.highlightAll()
}

watch(() => props.html, () => nextTick(enhance))
onMounted(() => nextTick(enhance))

const EMOJI = {
  ':blue_book:': '\u{1F4D8}', ':clipboard:': '\u{1F4CB}', ':thinking:': '\u{1F914}',
  ':dart:': '\u{1F3AF}', ':calendar_spiral:': '\u{1F5D3}', ':triangular_flag_on_post:': '\u{1F6A9}',
  ':link:': '\u{1F517}', ':card_box:': '\u{1F5C3}', ':white_check_mark:': '\u2705',
  ':star2:': '\u{1F31F}', ':goal:': '\u{1F3AF}', ':art:': '\u{1F3A8}',
  ':speaking_head:': '\u{1F5E3}', ':arrow_heading_up:': '\u2934\uFE0F',
  ':busts_in_silhouette:': '\u{1F465}', ':rainbow:': '\u{1F308}',
  ':books:': '\u{1F4DA}', ':plus:': '\u2795', ':minus:': '\u2796',
  ':warning:': '\u26A0\uFE0F', ':bulb:': '\u{1F4A1}', ':memo:': '\u{1F4DD}',
  ':gear:': '\u2699\uFE0F', ':rocket:': '\u{1F680}', ':lock:': '\u{1F512}',
  ':key:': '\u{1F511}', ':mag:': '\u{1F50D}', ':wrench:': '\u{1F527}',
  ':file_folder:': '\u{1F4C1}', ':chart_with_upwards_trend:': '\u{1F4C8}',
  ':construction:': '\u{1F6A7}',
}
</script>

<style>
/* Table scroll wrapper */
.confluence-content .table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 1.25rem 0;
  border: 1px solid oklch(0.92 0.006 60);
  border-radius: 10px;
}
.confluence-content .table-wrap table {
  margin: 0;
  border: none;
}

/* Status badge */
.confluence-content .status-badge {
  font-family: var(--font-ui);
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 0.75rem;
  font-weight: 500;
  background: oklch(0.96 0.006 60);
  color: oklch(0.38 0.015 50);
  border: 1px solid oklch(0.93 0.006 60);
}

/* Image placeholder */
.confluence-content .img-placeholder {
  border-radius: 10px;
  border: 1px dashed oklch(0.90 0.006 60);
  background: oklch(0.98 0.003 60);
  padding: 1.25rem;
  font-size: 0.8125rem;
  color: oklch(0.55 0.015 50);
  text-align: center;
  margin: 1rem 0;
}

/* Code copy button */
.confluence-content pre .copy-btn {
  font-family: var(--font-ui);
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 3px 10px;
  font-size: 11px;
  color: oklch(0.6 0.01 50);
  background: oklch(0.22 0.015 50);
  border: 1px solid oklch(0.30 0.015 50);
  border-radius: 6px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
}
.confluence-content pre:hover .copy-btn { opacity: 1; }
.confluence-content pre .copy-btn:hover { background: oklch(0.28 0.015 50); }
.confluence-content pre .copy-btn.copied { color: oklch(0.65 0.13 160); }

/* Heading anchor */
.confluence-content .anchor-link {
  position: absolute;
  left: -1.2em;
  color: transparent;
  text-decoration: none;
  font-weight: 400;
  transition: color 0.15s;
}
.confluence-content .group:hover .anchor-link {
  color: oklch(0.44 0.11 170 / 0.4);
}
</style>

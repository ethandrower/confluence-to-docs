/**
 * Concurrency primitives for the upload path.
 *
 * Two kinds of work share ONE ceiling here, deliberately. A whole small file
 * and a single part of a large one are both just "one PUT in flight", and the
 * browser's ~6-connections-per-host limit does not care which it is. Giving
 * files and parts separate budgets would let a batch of large files open
 * files×parts sockets and get *slower* through contention.
 */

// Below the browser's per-host cap, leaving room for the API calls that
// bracket each upload (init/complete go to our origin, the PUT does not).
export const UPLOAD_CONCURRENCY = 4

/** Error thrown when the server refuses an upload slot (HTTP 429). Carries
 *  how long to wait, so the queue backs off instead of guessing. */
export class RateLimited extends Error {
  constructor(retryAfterMs) {
    super('Too many uploads right now')
    this.name = 'RateLimited'
    this.retryAfterMs = retryAfterMs
  }
}

/**
 * Counting semaphore. `acquire()` resolves when a slot is free; every
 * acquire must be paired with exactly one `release()`.
 */
export function createSemaphore(limit = UPLOAD_CONCURRENCY) {
  let active = 0
  const waiting = []
  return {
    acquire() {
      if (active < limit) {
        active++
        return Promise.resolve()
      }
      return new Promise((resolve) => waiting.push(resolve))
    },
    release() {
      const next = waiting.shift()
      // Hand the slot straight to the next waiter rather than decrementing
      // and letting it re-race for it.
      if (next) next()
      else active = Math.max(0, active - 1)
    },
    get active() {
      return active
    },
    get queued() {
      return waiting.length
    },
  }
}

/**
 * A shared pause. When the server says "slow down", every worker waits on the
 * same barrier rather than each backing off independently — otherwise N
 * workers would each retry and each earn another 429.
 *
 * `onTick` receives the seconds remaining (0 when the pause lifts), which is
 * what lets the UI say "resuming in 42s" instead of appearing hung.
 */
export function createGate(onTick) {
  let barrier = null
  let releaseAt = 0

  return {
    /** Resolves immediately unless a pause is in force. */
    async pass() {
      while (barrier) await barrier
    },

    /**
     * Hold every worker for `ms`. Idempotent by design: concurrent 429s
     * extend one shared pause rather than stacking several.
     */
    pause(ms) {
      const end = Date.now() + ms
      if (end <= releaseAt) return // already covered by the running pause
      releaseAt = end
      if (barrier) return // the existing tick loop will observe the new end

      barrier = new Promise((resolve) => {
        const tick = () => {
          const left = releaseAt - Date.now()
          if (left <= 0) {
            barrier = null
            onTick?.(0)
            resolve()
            return
          }
          onTick?.(Math.ceil(left / 1000))
          setTimeout(tick, 250)
        }
        tick()
      })
    },

    get paused() {
      return !!barrier
    },
  }
}

/**
 * Run `task` over every item with at most `limit` in flight.
 *
 * Unlike Promise.all over a mapped array this never lets rejections escape:
 * one bad file must not abandon the other 499. Results come back in input
 * order as {ok, value, error}.
 */
export async function runPool(items, task, limit = UPLOAD_CONCURRENCY) {
  const results = new Array(items.length)
  let cursor = 0

  async function worker() {
    while (cursor < items.length) {
      const i = cursor++
      try {
        results[i] = { ok: true, value: await task(items[i], i) }
      } catch (error) {
        results[i] = { ok: false, error }
      }
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, worker)
  )
  return results
}

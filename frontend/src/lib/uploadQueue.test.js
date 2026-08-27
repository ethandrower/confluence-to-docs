import { describe, it, expect, vi } from 'vitest'
import { createSemaphore, createGate, runPool, RateLimited, UPLOAD_CONCURRENCY } from './uploadQueue.js'

const tick = () => new Promise((r) => setTimeout(r, 0))

describe('createSemaphore', () => {
  it('lets `limit` holders through and makes the rest wait', async () => {
    const s = createSemaphore(2)
    await s.acquire()
    await s.acquire()
    expect(s.active).toBe(2)

    let third = false
    s.acquire().then(() => (third = true))
    await tick()
    expect(third).toBe(false)
    expect(s.queued).toBe(1)

    s.release()
    await tick()
    expect(third).toBe(true)
  })

  it('hands a released slot straight to the next waiter', async () => {
    // Releasing must not drop `active` while someone is queued, or the pool
    // would briefly run over its own limit.
    const s = createSemaphore(1)
    await s.acquire()
    s.acquire()
    await tick()
    s.release()
    await tick()
    expect(s.active).toBe(1)
    expect(s.queued).toBe(0)
  })

  it('never lets active go negative on an over-release', async () => {
    const s = createSemaphore(1)
    await s.acquire()
    s.release()
    s.release()
    expect(s.active).toBe(0)
  })
})

describe('createGate', () => {
  it('passes immediately when no pause is in force', async () => {
    const g = createGate()
    await expect(g.pass()).resolves.toBeUndefined()
    expect(g.paused).toBe(false)
  })

  it('holds callers until the pause lifts, then releases them', async () => {
    vi.useFakeTimers()
    try {
      const g = createGate()
      g.pause(1000)
      expect(g.paused).toBe(true)

      let through = false
      g.pass().then(() => (through = true))
      await vi.advanceTimersByTimeAsync(500)
      expect(through).toBe(false)

      await vi.advanceTimersByTimeAsync(600)
      expect(through).toBe(true)
      expect(g.paused).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('merges concurrent pauses instead of stacking them', async () => {
    // Several workers hitting 429 at once must extend ONE barrier. Stacking
    // would multiply the wait by the number of workers.
    vi.useFakeTimers()
    try {
      const g = createGate()
      g.pause(1000)
      g.pause(3000)
      g.pause(500) // shorter than what is already running — must not shorten it

      let through = false
      g.pass().then(() => (through = true))

      await vi.advanceTimersByTimeAsync(2000)
      expect(through).toBe(false) // the 3000 pause still governs

      await vi.advanceTimersByTimeAsync(1200)
      expect(through).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports seconds remaining so the UI can count down', async () => {
    vi.useFakeTimers()
    try {
      const seen = []
      const g = createGate((s) => seen.push(s))
      g.pause(2000)
      await vi.advanceTimersByTimeAsync(2400)
      expect(seen[0]).toBe(2)
      expect(seen.at(-1)).toBe(0) // 0 signals "resumed"
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('runPool', () => {
  it('never exceeds the concurrency limit', async () => {
    let inFlight = 0
    let peak = 0
    const items = Array.from({ length: 20 }, (_, i) => i)

    await runPool(items, async () => {
      inFlight++
      peak = Math.max(peak, inFlight)
      await tick()
      inFlight--
    }, 4)

    expect(peak).toBe(4)
  })

  it('keeps going when one item throws, and reports per item', async () => {
    // The whole point: one bad file must not abandon the other 499.
    const items = ['a', 'bad', 'c']
    const results = await runPool(items, async (x) => {
      if (x === 'bad') throw new Error('nope')
      return x.toUpperCase()
    }, 2)

    expect(results.map((r) => r.ok)).toEqual([true, false, true])
    expect(results[0].value).toBe('A')
    expect(results[1].error.message).toBe('nope')
    expect(results[2].value).toBe('C')
  })

  it('returns results in input order despite out-of-order completion', async () => {
    const items = [30, 10, 20]
    const results = await runPool(items, async (ms) => {
      await new Promise((r) => setTimeout(r, ms))
      return ms
    }, 3)
    expect(results.map((r) => r.value)).toEqual([30, 10, 20])
  })

  it('handles an empty list without spawning workers', async () => {
    const task = vi.fn()
    await expect(runPool([], task)).resolves.toEqual([])
    expect(task).not.toHaveBeenCalled()
  })

  it('processes every item when there are more items than workers', async () => {
    const items = Array.from({ length: 50 }, (_, i) => i)
    const results = await runPool(items, async (i) => i * 2, 4)
    expect(results).toHaveLength(50)
    expect(results.every((r) => r.ok)).toBe(true)
    expect(results.at(-1).value).toBe(98)
  })
})

describe('RateLimited', () => {
  it('carries the wait so the queue does not have to guess', () => {
    const e = new RateLimited(60000)
    expect(e).toBeInstanceOf(Error)
    expect(e.retryAfterMs).toBe(60000)
    expect(e.name).toBe('RateLimited')
  })
})

it('keeps concurrency under the browser per-host connection cap', () => {
  expect(UPLOAD_CONCURRENCY).toBeLessThanOrEqual(6)
})

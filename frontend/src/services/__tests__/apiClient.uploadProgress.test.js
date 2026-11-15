import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../apiClient'

class FakeXhr {
  static last
  constructor() { this.upload = {}; this.headers = {}; FakeXhr.last = this }
  open(method, url) { this.method = method; this.url = url }
  setRequestHeader(k, v) { this.headers[k] = v }
  send(body) {
    this.body = body
    this.upload.onprogress({ lengthComputable: true, loaded: 5, total: 10 })
    this.status = this.reply.status
    this.responseText = JSON.stringify(this.reply.body)
    this.onload()
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('apiClient.upload', () => {
  it('reports progress through XHR and sends the FormData as is', async () => {
    vi.stubGlobal('XMLHttpRequest', class extends FakeXhr {
      constructor() { super(); this.reply = { status: 200, body: { data: { ok: 1 } } } }
    })
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    const form = new FormData()
    const onProgress = vi.fn()
    const out = await apiClient.upload('/system/restore', form, { onProgress })
    expect(out.data.ok).toBe(1)
    expect(onProgress).toHaveBeenCalledWith(5, 10)
    expect(FakeXhr.last.body).toBe(form)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('keeps the server message of a refusal', async () => {
    vi.stubGlobal('XMLHttpRequest', class extends FakeXhr {
      constructor() { super(); this.reply = { status: 413, body: { message: 'a restore accepts up to 512 MB' } } }
    })
    await expect(apiClient.upload('/x', new FormData(), { onProgress: () => {} }))
      .rejects.toMatchObject({ status: 413, message: 'a restore accepts up to 512 MB' })
  })

  it('uses fetch when no one asks for progress', async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ data: 1 }) }))
    vi.stubGlobal('fetch', fetchSpy)
    await apiClient.upload('/x', new FormData())
    expect(fetchSpy).toHaveBeenCalled()
  })
})

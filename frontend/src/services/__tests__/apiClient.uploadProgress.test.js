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

describe('apiClient.upload with a body that is not JSON', () => {
  const htmlPage = () => Promise.reject(new SyntaxError('Unexpected token <'))

  it('keeps the status of a proxy 413 and says what refused it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 413, json: htmlPage })))
    const err = await apiClient.upload('/system/restore', new FormData()).catch((e) => e)
    expect(err.status).toBe(413)
    expect(err.message).toBe('The server or a proxy in front of it refused a request of this size.')
  })

  it('does the same through XHR when progress is asked', async () => {
    class Html extends FakeXhr {
      send(body) {
        this.body = body
        this.status = 413
        this.responseText = '<html><body>413 Request Entity Too Large</body></html>'
        this.onload()
      }
    }
    vi.stubGlobal('XMLHttpRequest', Html)
    const err = await apiClient.upload('/system/restore', new FormData(), { onProgress: () => {} }).catch((e) => e)
    expect(err.status).toBe(413)
    expect(err.message).toMatch(/proxy/)
  })

})

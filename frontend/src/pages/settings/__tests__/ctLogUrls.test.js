import { describe, expect, it } from 'vitest'
import { addCtLogUrl, removeCtLogUrl } from '../ctLogUrls'

describe('CT log list while the built-in logs apply (log_urls null)', () => {
  it('adding a URL starts a list instead of throwing', () => {
    expect(addCtLogUrl(null, 'https://ct.example/')).toEqual(['https://ct.example/'])
  })
  it('removing from no list gives an empty list', () => {
    expect(removeCtLogUrl(null, 0)).toEqual([])
  })
  it('a URL already listed is not added twice', () => {
    expect(addCtLogUrl(['https://a/'], 'https://a/')).toEqual(['https://a/'])
  })
})

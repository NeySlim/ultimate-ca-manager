// log_urls is null while the built-in CT logs apply: the first URL added starts a list of its own.
export function addCtLogUrl(urls, url) {
  const list = urls || []
  return list.includes(url) ? list : [...list, url]
}

export function removeCtLogUrl(urls, index) {
  return (urls || []).filter((_, i) => i !== index)
}

import { guideHeadings, renderMarkdown } from './markdown'

/** A whole chapter, its `##` included; levelOffset shifts the heading levels under a host's own title. */
export function GuideContent({ chapter, markdown, englishMarkdown, levelOffset = 0 }) {
  const ids = guideHeadings(chapter, markdown, englishMarkdown ?? markdown).map((h) => h.id)
  return <>{renderMarkdown((markdown || '').split('\n'), { ids, levelOffset })}</>
}

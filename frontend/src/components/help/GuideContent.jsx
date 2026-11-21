import { guideHeadings, renderMarkdown } from './markdown'
import { highlightTree } from './highlight'

/**
 * A whole chapter, its `##` included; levelOffset shifts the heading levels under a host's own title;
 * highlight: folded search terms marked in the rendered text.
 */
export function GuideContent({ chapter, markdown, englishMarkdown, levelOffset = 0, highlight }) {
  const ids = guideHeadings(chapter, markdown, englishMarkdown ?? markdown).map((h) => h.id)
  const nodes = renderMarkdown((markdown || '').split('\n'), { ids, levelOffset })
  return <>{highlight?.length ? highlightTree(nodes, highlight) : nodes}</>
}

/**
 * ReactMarkdown output (release notes, terms of service) under the mockup's typography: headings as
 * its section titles, lists indented as its help lists, links as its text links.
 */
export const MARKDOWN_COMPONENTS = {
  h1: ({ children }) => <h3 className="section-title">{children}</h3>,
  h2: ({ children }) => <h3 className="section-title">{children}</h3>,
  h3: ({ children }) => <h3 className="section-title">{children}</h3>,
  ul: ({ children }) => <ul style={{ paddingLeft: 17, margin: '4px 0 12px' }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ paddingLeft: 17, margin: '4px 0 12px' }}>{children}</ol>,
  p: ({ children }) => <p style={{ margin: '0 0 8px' }}>{children}</p>,
  a: ({ href, children }) => <a className="text-link" href={href} target="_blank" rel="noreferrer">{children}</a>,
  code: ({ children }) => <code className="mono">{children}</code>,
}

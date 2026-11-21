/**
 * The mockup's pageHead() and moduleHead(): the title (focused by script after a navigation),
 * the total in words, one sentence of intent, then the page actions, the main one last.
 */
export function PageHead({ title, total, intent, actions }) {
  return (
    <header className="page-head">
      <div>
        <div className="title-line">
          <h1 id="main-title" tabIndex={-1}>{title}</h1>
          <span className="total">{total ?? ''}</span>
        </div>
        {intent && <p>{intent}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  )
}

export default PageHead

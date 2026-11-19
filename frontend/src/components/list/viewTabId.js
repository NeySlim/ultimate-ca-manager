/** Id of a state tab, so the panel it filters can name it. */
export const viewTabId = (baseId, id) => `${baseId}-tab-${id === '' ? 'all' : id}`

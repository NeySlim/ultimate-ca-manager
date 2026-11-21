// English structure, translated text where the language has it
export function mergeHelpContent(en, tr) {
  if (!tr) return en
  return {
    ...en,
    title: tr.title || en.title,
    subtitle: tr.subtitle || en.subtitle,
    overview: tr.overview || en.overview,
    sections: en.sections?.map((sec, i) => ({
      ...sec,
      title: tr.sections?.[i]?.title || sec.title,
      content: tr.sections?.[i]?.content ?? sec.content,
      items: sec.items?.map((item, j) => {
        const trItem = tr.sections?.[i]?.items?.[j]
        if (!trItem) return item
        if (typeof item === 'string') return trItem
        return { ...item, label: trItem?.label || item.label, text: trItem?.text || item.text }
      }),
      definitions: sec.definitions?.map((def, j) => ({
        ...def,
        term: tr.sections?.[i]?.definitions?.[j]?.term || def.term,
        description: tr.sections?.[i]?.definitions?.[j]?.description || def.description,
      })),
      example: tr.sections?.[i]?.example ?? sec.example,
    })),
    tips: tr.tips || en.tips,
    warnings: tr.warnings || en.warnings,
    related: en.related,
  }
}

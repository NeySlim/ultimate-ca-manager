// Loads one translated help page; only the languages in helpLanguages.js have files.
export const loadHelpPage = (langKey, pageKey) => import(`./help/${langKey}/${pageKey}.js`)

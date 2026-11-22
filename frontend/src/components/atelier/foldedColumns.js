/** The columns a list folded for want of room (DataTable), read by its footer to say so (TableFooter). */
import { createContext } from 'react'

export const FoldedColumns = createContext(null)

/** Réinitialiser les colonnes of a list while a width is set by hand (DataTable), offered by its footer (C2). */
export const ColumnsReset = createContext(null)

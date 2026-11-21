// A detail URL (/certificates/12) belongs to its list page
export const pageOf = (pathname) => pathname.replace(/\/\d+\/?$/, '') || '/'

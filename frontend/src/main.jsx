import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
// The mockup's sheets: the shell and the sign-in pages are drawn with them on every page
import './styles/atelier/scope.css'
import './styles/atelier/maquette.css'
import './styles/atelier/extensions.css'
import './i18n'
import { takeOverServedGuide } from './ssr/takeOver'

const container = document.getElementById('root')
const app = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

// A guide chapter the server drew is hydrated as it stands; any other page is drawn afresh
takeOverServedGuide(container).catch(() => false).then((served) => {
  if (served) ReactDOM.hydrateRoot(container, app)
  else ReactDOM.createRoot(container).render(app)
})

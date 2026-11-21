import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
// The mockup's sheets: the shell and the sign-in pages are drawn with them on every page
import './styles/atelier/scope.css'
import './styles/atelier/maquette.css'
import './styles/atelier/extensions.css'
import './i18n'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

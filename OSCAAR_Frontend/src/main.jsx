import React from 'react'
import ReactDOM from 'react-dom/client'
import './i18n/translations.js'
import './styles/theme.css'
import { AuthProvider } from './context/AuthContext'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <App/>
    </AuthProvider>
  </React.StrictMode>
)

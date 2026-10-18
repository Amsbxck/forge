import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import Fehlergrenze from './components/Fehlergrenze'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Fehlergrenze>
      <App />
    </Fehlergrenze>
  </React.StrictMode>
)

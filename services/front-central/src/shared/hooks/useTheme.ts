import { useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'

// Preferencia de tema del navegador. Es solo comodidad visual: si el
// almacenamiento falla o está bloqueado se usa el tema claro.
function readTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useEffect(() => {
    // Bootstrap 5.3 cambia todos sus colores según este atributo.
    document.documentElement.setAttribute('data-bs-theme', theme)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // sin almacenamiento el tema dura solo esta visita
    }
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  return { theme, toggleTheme }
}

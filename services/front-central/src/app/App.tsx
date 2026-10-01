import { useEffect } from 'react'
import { RouterProvider } from 'react-router/dom'
import { router } from './router'
import { useSessionStore } from '../shared/auth/sessionStore'
import ToastContainer from '../shared/components/ToastContainer'

export default function App() {
  const initialize = useSessionStore((s) => s.initialize)

  // Recupera la sesión al cargar la página (refresh guardado en la pestaña).
  useEffect(() => {
    initialize()
  }, [initialize])

  return (
    <>
      <RouterProvider router={router} />
      <ToastContainer />
    </>
  )
}

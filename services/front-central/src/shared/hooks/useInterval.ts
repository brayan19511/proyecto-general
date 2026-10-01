import { useEffect, useRef } from 'react'

// Ejecuta `callback` cada `ms` mientras `active` sea true. Se usa para seguir
// trabajos del worker (sincronizaciones, reclasificaciones): el 202 del POST no
// es el fin del trabajo. Se detiene al desmontar el componente.
export function useInterval(active: boolean, callback: () => void, ms: number) {
  const saved = useRef(callback)

  useEffect(() => {
    saved.current = callback
  }, [callback])

  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => saved.current(), ms)
    return () => clearInterval(timer)
  }, [active, ms])
}

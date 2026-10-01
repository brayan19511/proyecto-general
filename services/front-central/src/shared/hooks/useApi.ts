import { useCallback, useEffect, useState, type DependencyList } from 'react'
import { ApiError } from '../api/apiClient'

type Result<T> = {
  key: string // solicitud a la que corresponde este resultado
  data?: T
  error?: string
}

/**
 * Carga datos al montar el componente y cada vez que cambian `deps`.
 *
 *   const { data, loading, error, reload } = useApi(() => service.list(filtro), [filtro])
 *
 * - `deps` deben ser valores simples (ids, textos, filtros): forman la clave.
 * - Mientras recarga conserva los datos anteriores (la tabla no parpadea).
 * - Descarta respuestas viejas si `deps` cambió antes de que llegaran.
 * - `setData` reemplaza los datos sin volver a pedirlos (p. ej. tras un PATCH).
 */
export function useApi<T>(loader: () => Promise<T>, deps: DependencyList = []) {
  const [version, setVersion] = useState(0)
  const key = `${JSON.stringify(deps)}#${version}`
  const [result, setResult] = useState<Result<T>>({ key: '' })

  useEffect(() => {
    let active = true
    loader().then(
      (data) => active && setResult({ key, data }),
      (error) => active && setResult({ key, error: errorMessage(error) }),
    )
    return () => {
      active = false
    }
    // La clave resume deps y recargas; `loader` cambia en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  const setData = useCallback((data: T) => setResult((r) => ({ ...r, data })), [])

  return {
    data: result.data,
    error: result.key === key ? result.error : undefined,
    loading: result.key !== key,
    reload,
    setData,
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  // Un error que no viene de la API es un fallo del front: se deja en la consola
  // para poder corregirlo (nunca contiene tokens: no son respuestas del servidor).
  console.error(error)
  return 'Ocurrió un error inesperado.'
}

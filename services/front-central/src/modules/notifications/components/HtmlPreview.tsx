import { useEffect, useRef } from 'react'

// Cuerpo HTML de un correo. Viene de terceros (plantillas, consumidores), así
// que se muestra en public/email-preview.html dentro de un iframe con sandbox
// "allow-scripts" SIN allow-same-origin: otro origen (opaco), sin acceso a la
// sesión ni a la página del front. Esa página tiene su propia CSP (nginx):
// admite los estilos en línea del correo, pero no sus scripts ni imágenes
// externas (que además evita rastreo al abrir el correo).
export default function HtmlPreview({ html, title }: { html: string; title: string }) {
  const frame = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    let sent = false
    const onMessage = (event: MessageEvent) => {
      // Solo el aviso de nuestro iframe, y se responde una vez: si el marco
      // llegara a cargar otra cosa, no recibe el contenido de nuevo.
      if (sent || event.source !== frame.current?.contentWindow) return
      if ((event.data as { type?: string })?.type !== 'email-preview-ready') return
      sent = true
      // Origen opaco: no hay un targetOrigin concreto; por eso el control de
      // source y el envío único.
      frame.current?.contentWindow?.postMessage({ type: 'email-preview', html }, '*')
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [html])

  return (
    <iframe
      // key: con otro HTML se recarga la página y se repite el saludo.
      key={html}
      ref={frame}
      title={title}
      src="/email-preview.html"
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      className="w-100 border rounded-3 bg-white"
      style={{ height: 420 }}
    />
  )
}

// Copiar texto al portapapeles también sin HTTPS. navigator.clipboard solo
// existe en contextos seguros (HTTPS o localhost); en la red por HTTP se usa el
// método anterior (un textarea temporal + execCommand), que todos los
// navegadores siguen admitiendo. Devuelve false si no se pudo.
export async function copyText(text: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // permiso denegado: probar el método anterior
    }
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(area)
  }
}

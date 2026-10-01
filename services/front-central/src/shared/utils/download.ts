// Guarda un archivo generado o recibido en el navegador.
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export type CsvColumn<T> = { header: string; value: (row: T) => string | number | null | undefined }

// CSV con ";" y BOM UTF-8 para que Excel en español lo abra con acentos y
// columnas separadas. Los valores se escriben tal como llegan (importes con
// punto decimal y signo, fechas AAAA-MM-DD).
export function toCsv<T>(rows: T[], columns: CsvColumn<T>[]): Blob {
  const escape = (value: string | number | null | undefined) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[;"\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const lines = [
    columns.map((c) => escape(c.header)).join(';'),
    ...rows.map((row) => columns.map((c) => escape(c.value(row))).join(';')),
  ]
  return new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
}

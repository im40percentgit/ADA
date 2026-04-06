/**
 * usePdfExport — hook for exporting DOM elements to PDF.
 *
 * Dynamically imports html2canvas and jsPDF on first use (code-splitting)
 * to avoid bloating the main bundle. Captures the target element at 2x
 * scale for crisp output, then fits it onto an A4 page with 10mm margins.
 *
 * @decision DEC-FRONTEND-075
 * @title PDF export uses dynamic import for html2canvas + jsPDF
 * @status accepted
 * @rationale html2canvas (~250KB) and jsPDF (~300KB) are heavy libraries
 *   used only on explicit user action. Dynamic import() keeps them out of
 *   the critical path and loads them only when the user clicks "Download PDF".
 */

import { useState } from 'react'

export function usePdfExport() {
  const [exporting, setExporting] = useState(false)

  const exportToPdf = async (elementId: string, filename: string) => {
    setExporting(true)
    try {
      const element = document.getElementById(elementId)
      if (!element) return

      const html2canvas = (await import('html2canvas')).default
      const { jsPDF } = await import('jspdf')

      const canvas = await html2canvas(element, {
        scale: 2,
        backgroundColor: '#1c1917',
      })

      const pdf = new jsPDF('p', 'mm', 'a4')
      const imgWidth = 190
      const imgHeight = (canvas.height * imgWidth) / canvas.width
      pdf.addImage(
        canvas.toDataURL('image/png'),
        'PNG',
        10,
        10,
        imgWidth,
        imgHeight,
      )
      pdf.save(filename)
    } finally {
      setExporting(false)
    }
  }

  return { exportToPdf, exporting }
}

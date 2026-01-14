import './globals.css'
import type { Metadata } from 'next'
import { Inter, Libre_Baskerville } from 'next/font/google'

const inter = Inter({ 
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
})

const libreBaskerville = Libre_Baskerville({ 
  weight: ['400', '700'],
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Lexora - Legal Contract Analysis Platform',
  description: 'AI-powered contract analysis with clause classification and risk scoring',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${inter.variable} ${libreBaskerville.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  )
}

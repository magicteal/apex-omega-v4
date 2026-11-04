import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'APEX-OMEGA OS // Command Center',
  description: 'Quantitative Trading Command Center - TTM Squeeze, Hyper-Kelly & Vault Siphon Protocol',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-text min-h-screen selection:bg-accent selection:text-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}

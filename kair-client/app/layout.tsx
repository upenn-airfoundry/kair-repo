import React from 'react';
import './globals.css';
import type { Metadata } from 'next';
import { AppShell } from '@/components/app-shell';

export const metadata: Metadata = {
  title: 'KAIR',
  description: 'Semantic Search Prototype',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-dvh overflow-hidden flex flex-col">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

import React, { Suspense } from 'react';
import './globals.css';
import type { Metadata } from 'next';
import { AppShell } from '@/components/app-shell';
import SessionKeepalive from '@/components/session-keepalive';

export const metadata: Metadata = {
  title: 'KAIR',
  description: 'Semantic Search Prototype',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-dvh overflow-hidden flex flex-col">
        <SessionKeepalive />
        <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading…</div>}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  );
}

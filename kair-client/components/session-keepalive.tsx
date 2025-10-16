'use client';

import { useEffect, useRef } from 'react';
import { config } from '@/config';

export default function SessionKeepalive() {
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let stopped = false;

    const ping = async () => {
      try {
        await fetch(`${config.apiBaseUrl}/api/session/keepalive`, {
          method: 'GET',
          credentials: 'include',
          cache: 'no-store',
        });
      } catch {
        // ignore
      }
    };

    const start = () => {
      // Initial ping on mount and on visibility gain
      ping();
      // Every 2 minutes by default
      timerRef.current = window.setInterval(() => {
        if (!document.hidden) {
          ping();
        }
      }, 2 * 60 * 1000);
    };

    const stop = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };

    const onVisibility = () => {
      if (stopped) return;
      if (!document.hidden && !timerRef.current) start();
      if (document.hidden && timerRef.current) stop();
      // Also ping immediately when the tab becomes visible again
      if (!document.hidden) ping();
    };

    start();
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stopped = true;
      document.removeEventListener('visibilitychange', onVisibility);
      stop();
    };
  }, []);

  return null;
}
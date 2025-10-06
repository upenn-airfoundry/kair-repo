'use client';

import { useRouter } from 'next/navigation';
import { useCallback } from 'react';
import { useAuth } from '@/context/auth-context';

export const useSecureFetch = () => {
  const router = useRouter();
  const { logout } = useAuth();

  const secureFetch = useCallback(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    // Ensure credentials are always included
    const options = {
      ...init,
      credentials: 'include' as const,
    };

    const response = await fetch(input, options);

    if (response.status === 401) {
      // Clear user session data
      logout();
      // Redirect to the login page
      router.push('/login');
      // Throw an error to stop further processing in the calling function
      throw new Error('Session expired or user is not authenticated.');
    }

    return response;
  }, [router, logout]);

  return secureFetch;
};
"use client";

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/auth-context';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  // Track if the check has been performed to avoid flicker/multiple redirects
  const [isChecking, setIsChecking] = React.useState(true);

  useEffect(() => {
    // Only redirect if auth state is definitive (not initial render potentially)
    // and the user is not authenticated.
    if (!isAuthenticated) {
        // Check ensures we don't redirect during initial check/context setup
        router.push('/login');
    } else {
        // If authenticated, stop checking
        setIsChecking(false);
    }
    // Dependency array ensures this runs when isAuthenticated changes
    // We don't strictly need router in deps as it's stable from next/navigation
  }, [isAuthenticated, router]); // Add router to dependency array

  // While checking, potentially show a loader or null
  if (isChecking && !isAuthenticated) {
    // Improved check: If still checking and not authenticated, show nothing/loader
    // This prevents brief flashing of protected content before redirect
    return null; // Or return a loading spinner component
  }

  // If authenticated, render the children
  return <>{children}</>;
} 
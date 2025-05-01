import { redirect } from 'next/navigation';

export default function Home() {
  // Dummy authentication state - replace with actual auth logic later
  const isAuthenticated = true; // Set to false to test the /login redirect

  if (isAuthenticated) {
    redirect('/dashboard');
  } else {
    redirect('/login');
  }

  // The component will redirect before reaching this point,
  // so we can return null or an empty fragment.
  return null;
}

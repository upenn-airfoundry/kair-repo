'use client';

import Image from 'next/image';
import Link from 'next/link';
import { NavUser } from '@/components/nav-user';
import { useAuth } from '@/context/auth-context';
// import { SidebarTrigger } from '@/components/ui/sidebar';

export function HeaderBar() {
  const { user } = useAuth();
  return (
    <header className="relative h-14 flex-none border-b bg-white/80 backdrop-blur">
      {/* Penn-inspired color gradient bar */}
      <div className="absolute top-0 left-0 right-0 h-0.5 bg-[linear-gradient(to_right,#990000,#011F5B)]" />
      
      {/* Subtle background shade */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top_left,rgba(153,0,0,0.03),transparent_90%),radial-gradient(ellipse_at_top_right,rgba(1,31,91,0.03),transparent_90%)]" />

      <div className="h-full px-3 sm:px-4 flex items-center gap-3">
        {/* <SidebarTrigger className="mr-1" /> */}
        <Link href="/" className="flex items-center gap-2">
          <Image
            src="/images/airfoundry-badge.png"
            alt="KAIR"
            width={40}
            height={40}
            className="rounded"
            priority
          />
          <span className="text-sm sm:text-base font-semibold text-gray-900">KAIR Assistant @ AIRFoundry</span>
        </Link>
        <div className="ml-auto">
          <NavUser
            user={{
              name: user?.name || 'User',
              email: user?.email || '',
              avatar: user?.avatar || '/avatars/shadcn.jpg'
            }}
          />
        </div>
      </div>
    </header>
  );
}
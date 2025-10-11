'use client';

import Image from 'next/image';
import Link from 'next/link';
import { NavUser } from '@/components/nav-user';
import { useAuth } from '@/context/auth-context';
// import { SidebarTrigger } from '@/components/ui/sidebar';

export function HeaderBar() {
  const { user } = useAuth();
  return (
    <header className="h-14 flex-none border-b bg-white/80 backdrop-blur">
      <div className="h-full px-3 sm:px-4 flex items-center gap-3">
        {/* <SidebarTrigger className="mr-1" /> */}
        <Link href="/" className="flex items-center gap-2">
          <Image
            src="/images/airfoundry-badge.png"
            alt="KAIR"
            width={28}
            height={28}
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
              avatar: user?.avatar || '/avatars/shadcn.jpg',
              organization: user?.organization || 'KAIR',
            }}
          />
        </div>
      </div>
    </header>
  );
}
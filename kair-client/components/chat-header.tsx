import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import Image from "next/image"
import { useAuth } from "@/context/auth-context";

interface ChatHeaderProps {
  title: string;
  description?: string;
}

export function ChatHeader({ title, description }: ChatHeaderProps) {
  const { user } = useAuth();
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mx-2 data-[orientation=vertical]:h-4"
        />
        <div className="flex flex-col">
            <h1 className="text-base font-medium flex items-center">
            <Image
              src="/images/airfoundry-logo.png"
              width={187}
              height={52}
              alt="Airfoundry Logo"
              className="inline-block mr-2"
            />&nbsp;&nbsp;
            {title}
            </h1>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
        <div>
          Discovery mode for {user.name} at {user.organization}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {/* Additional header elements can go here */}
        </div>
      </div>
    </header>
  )
} 

import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { ChatHeader } from '@/components/chat-header';
import { ProtectedRoute } from "@/components/protected-route"

export default function ProjectsPage() {
  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <ChatHeader title="Projects" />
        <div className="flex flex-1 flex-col">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex-grow p-4 overflow-y-auto border-t">
              <p className="text-center text-muted-foreground">Projects management content will appear here.</p>
            </div>
            {/* Add projects specific components here later */}
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
} 
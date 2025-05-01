import ChatInput from '@/components/chat-input';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter,
} from '@/components/ui/card';
import { ChatHeader } from '@/components/chat-header';

export default function ChatPage() {
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
        <ChatHeader />
        <div className="flex flex-1 flex-col">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex-grow p-4 overflow-y-auto border-t">
              <p className="text-center text-muted-foreground">Chat messages with KAIR will appear here.</p>
            </div>
            <ChatInput />
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
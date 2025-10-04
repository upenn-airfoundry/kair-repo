"use client";

import ChatInput from '@/components/chat-input';
import { Message } from '@/components/chat-input';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { ProtectedRoute } from "@/components/protected-route"
import { ChatHeader } from '@/components/chat-header';
import { useAuth } from '@/context/auth-context';
import { useState } from 'react';

export default function ChatPage() {
  const { user } = useAuth();

  const [, setMessages] = useState<Message[]>([]);

  // Determine the project ID from the user's session data
  // We'll use the first project in the list as the default.
  const projectId = user?.project_id;

  return (
    <ProtectedRoute>
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
        <ChatHeader title="" description={projectId?.toString()} />
        <div className="flex flex-1 flex-col">
          <div className="@container/main flex flex-1 flex-col gap-2">
            {projectId ? (
              <ChatInput 
                projectId={projectId}
                addMessage={(message: Message) => {
                  setMessages(prev => [...prev, message]);
                  console.log("New message:", message);
                }} 
              />
            ) : (
              <div className="p-4 text-center text-muted-foreground">
                Loading chat or no project selected...
              </div>
            )}
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
    </ProtectedRoute>
  );
}


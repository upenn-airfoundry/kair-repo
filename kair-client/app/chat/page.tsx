"use client";

import ChatInput from '@/components/chat-input';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar';
import { ProtectedRoute } from "@/components/protected-route"
import { useAuth } from '@/context/auth-context';
import { useState } from 'react';
import ProjectGraphPane from '@/components/project-graph-pane';
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import { Separator } from "@/components/ui/separator";

export interface Message {
  id: string;
  sender: 'user' | 'bot';
  content: string;
}

export default function ChatPage() {
  const { user } = useAuth();
  const [, setMessages] = useState<Message[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleRefreshRequest = () => {
    setRefreshKey(prevKey => prevKey + 1);
  };

  const projectId = user?.project_id;
  const projectName = user?.project_name;

            // <SidebarTrigger className="-ml-1" />
            // <Separator orientation="vertical" className="mr-2 h-4" />
          // <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
          //   <div className="text-sm font-semibold">
          //     {projectName || 'New KAIR Project'}
          //   </div>
          // </header>

  return (
    <ProtectedRoute>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PanelGroup direction="vertical" className="h-[calc(100vh-4rem)] w-full">
            <Panel defaultSize={25} minSize={15}>
              <div className="h-full w-full">
                {projectId && projectName ? (
                  <ProjectGraphPane
                    projectId={projectId}
                    projectName={projectName}
                    refreshKey={refreshKey}
                  />
                ) : (
                  <div className="h-full w-full border rounded-lg flex items-center justify-center text-muted-foreground">
                    Loading project workflow...
                  </div>
                )}
              </div>
            </Panel>

            <PanelResizeHandle className="h-2 flex items-center justify-center bg-muted transition-colors hover:bg-muted-foreground/20">
              <div className="w-8 h-1 rounded-full bg-border" />
            </PanelResizeHandle>

            <Panel defaultSize={75} minSize={20}>
              <div className="h-full w-full flex flex-col">
                {projectId ? (
                  <ChatInput
                    projectId={projectId}
                    addMessage={(message: Message) => {
                      setMessages(prev => [...prev, message]);
                    }}
                    onRefreshRequest={handleRefreshRequest}
                  />
                ) : (
                  <div className="p-4 text-center text-muted-foreground">
                    Loading chat or no project selected...
                  </div>
                )}
              </div>
            </Panel>
          </PanelGroup>
        </SidebarInset>
      </SidebarProvider>
    </ProtectedRoute>
  );
}


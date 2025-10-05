"use client";

import ChatInput from '@/components/chat-input';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { ProtectedRoute } from "@/components/protected-route"
import { useAuth } from '@/context/auth-context';
import { useState } from 'react';
import ProjectGraphPane from '@/components/project-graph-pane';
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";

export interface Message {
  id: string;
  sender: 'user' | 'bot';
  content: string;
}

export default function ChatPage() {
  const { user } = useAuth();
  const [, setMessages] = useState<Message[]>([]);
  const [refreshKey, setRefreshKey] = useState(0); // State to trigger refresh

  // Function to increment the key, causing a re-render in child components
  const handleRefreshRequest = () => {
    setRefreshKey(prevKey => prevKey + 1);
  };

  // Determine the project ID and name from the user's session data
  const projectId = user?.project_id;
  const projectName = user?.project_name;

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
          <PanelGroup direction="vertical" className="h-screen w-full">
            {/* Top Panel for Project Graph */}
            <Panel defaultSize={25} minSize={15}>
              <div className="h-full w-full">
                {projectId && projectName ? (
                  <ProjectGraphPane
                    projectId={projectId}
                    projectName={projectName}
                    refreshKey={refreshKey} // Pass the key as a prop
                  />
                ) : (
                  <div className="h-full w-full border rounded-lg flex items-center justify-center text-muted-foreground">
                    Loading project workflow...
                  </div>
                )}
              </div>
            </Panel>

            {/* Resizable Handle */}
            <PanelResizeHandle className="h-2 flex items-center justify-center bg-muted transition-colors hover:bg-muted-foreground/20">
              <div className="w-8 h-1 rounded-full bg-border" />
            </PanelResizeHandle>

            {/* Bottom Panel for Chat */}
            <Panel defaultSize={75} minSize={20}>
              <div className="h-full w-full flex flex-col">
                {projectId ? (
                  <ChatInput
                    projectId={projectId}
                    addMessage={(message: Message) => {
                      setMessages(prev => [...prev, message]);
                    }}
                    onRefreshRequest={handleRefreshRequest} // Pass the handler function
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


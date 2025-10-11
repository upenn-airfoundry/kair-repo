"use client";

import ChatInput from '@/components/chat-input';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar';
import { ProtectedRoute } from "@/components/protected-route"
import { useAuth } from '@/context/auth-context';
import { useEffect, useState } from "react";
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

  // NEW: hold the active project locally
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [activeProjectName, setActiveProjectName] = useState<string>("");

  useEffect(() => {
    // Initialize from user context if available
    if (user?.project_id) setActiveProjectId(user.project_id);
    if (user?.project_name) setActiveProjectName(user.project_name);
  }, [user?.project_id, user?.project_name]);

  // Listen to global project changes (from sidebar and graph pane)
  useEffect(() => {
    const handler = (e: any) => {
      const pid = Number(e?.detail?.projectId);
      if (Number.isFinite(pid)) {
        setActiveProjectId(pid);
        setRefreshKey(prev => prev + 1);
      }
    };
    window.addEventListener("project-changed", handler as any);
    return () => window.removeEventListener("project-changed", handler as any);
  }, []);

  const handleRefreshRequest = () => setRefreshKey(prevKey => prevKey + 1);

  // Called by ProjectGraphPane when user selects/creates a project
  const handleProjectChanged = (pid: number) => {
    setActiveProjectId(pid);
    // Name can be updated via account refetch if desired; for now keep existing
    setRefreshKey(prev => prev + 1); // trigger graph refresh
  };

  return (
    <ProtectedRoute>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PanelGroup direction="vertical" className="h-[calc(100vh-4rem)] w-full">
            <Panel defaultSize={25} minSize={15}>
              <div className="h-full w-full">
                {activeProjectId && activeProjectName ? (
                  <ProjectGraphPane
                    projectId={activeProjectId}
                    projectName={activeProjectName}
                    refreshKey={refreshKey}
                    onProjectChanged={handleProjectChanged}  // pass callback
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
                {activeProjectId ? (
                  <ChatInput
                    projectId={activeProjectId}                  // use active project
                    addMessage={(message: Message) => setMessages(prev => [...prev, message])}
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


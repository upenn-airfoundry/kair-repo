"use client";

import React, { useEffect, useState } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import ProjectGraphPane from "@/components/project-graph-pane";
import ChatInput from "@/components/chat-input";
import { ProtectedRoute } from "@/components/protected-route";
import { AppSidebar } from "@/components/app-sidebar"; // if you previously used it directly here, no longer needed
import { useAuth } from "@/context/auth-context";

export default function ChatPage() {
  const { user } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [activeProjectName, setActiveProjectName] = useState<string>("");

  useEffect(() => {
    if (user?.project_id) setActiveProjectId(user.project_id);
    if (user?.project_name) setActiveProjectName(user.project_name);
  }, [user?.project_id, user?.project_name]);

  useEffect(() => {
    const handler = (e: any) => {
      const pid = Number(e?.detail?.projectId);
      if (Number.isFinite(pid)) {
        setActiveProjectId(pid);
        setRefreshKey((k) => k + 1);
      }
    };
    window.addEventListener("project-changed", handler as any);
    return () => window.removeEventListener("project-changed", handler as any);
  }, []);

  const handleRefreshRequest = () => setRefreshKey((k) => k + 1);
  const handleProjectChanged = (pid: number) => {
    setActiveProjectId(pid);
    setRefreshKey((k) => k + 1);
  };

  return (
    <ProtectedRoute>
      {/* NOTE: SidebarProvider is now in AppShell (global). Do not use SidebarInset here. */}
      <div className="h-full w-full">
        <PanelGroup direction="vertical" className="h-full w-full">
          <Panel defaultSize={30} minSize={15}>
            <div className="h-full w-full">
              {activeProjectId && activeProjectName ? (
                <ProjectGraphPane
                  projectId={activeProjectId}
                  projectName={activeProjectName}
                  refreshKey={refreshKey}
                  onProjectChanged={handleProjectChanged}
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

          <Panel defaultSize={70} minSize={20}>
            <div className="h-full w-full flex flex-col">
              {activeProjectId ? (
                <ChatInput projectId={activeProjectId} onRefreshRequest={handleRefreshRequest} />
              ) : (
                <div className="p-4 text-center text-muted-foreground">
                  Loading chat or no project selected...
                </div>
              )}
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </ProtectedRoute>
  );
}


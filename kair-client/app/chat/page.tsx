"use client";

import React, { useEffect, useState } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import ProjectGraphPane from "@/components/project-graph-pane";
import ChatInput, { Message } from "@/components/chat-input";
import { ProtectedRoute } from "@/components/protected-route";
import { useAuth } from "@/context/auth-context";
import { useSecureFetch } from "@/hooks/useSecureFetch";
import { config } from "@/config";

export default function ChatPage() {
  const { user } = useAuth();
  const secureFetch = useSecureFetch();
  const [refreshKey, setRefreshKey] = useState(0);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [activeProjectName, setActiveProjectName] = useState<string>("");
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  // ChatInput manages its own message list; keep a typed no-op callback to satisfy props
  const addMessage: (message: Message) => void = React.useCallback(() => {
    // no-op; ChatInput manages messages internally
  }, []);

  useEffect(() => {
    if (user?.project_id) setActiveProjectId(user.project_id);
    if (user?.project_name) setActiveProjectName(user.project_name);
  }, [user?.project_id, user?.project_name]);

  useEffect(() => {
    const handler = (e: CustomEvent<{ projectId: number | null }>) => {
      const pid = e.detail.projectId;
      if (pid !== null && Number.isFinite(pid)) {
        setActiveProjectId(pid);
        // When project changes, we need to fetch its name
        secureFetch(`${config.apiBaseUrl}/api/projects/list?mine=1`)
          .then((res) => res.json())
          .then((data) => {
            const project = data?.projects?.find((p: { id: number }) => p.id === pid);
            if (project) {
              setActiveProjectName(project.name);
            }
          })
          .catch(() => setActiveProjectName("")); // Clear name on error
        setRefreshKey((k) => k + 1);
      } else {
        // Handle project deselection
        setActiveProjectId(null);
        setActiveProjectName("");
      }
      // Chat messages are managed by ChatInput; nothing to clear here
    };
    window.addEventListener("project-changed", handler as EventListener);
    return () => window.removeEventListener("project-changed", handler as EventListener);
  }, [secureFetch]);

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
                  onTaskSelected={setSelectedTaskId}
                />
              ) : (
                <div className="h-full w-full border rounded-lg flex items-center justify-center text-muted-foreground">
                  {user ? "Select a project to begin." : "Loading project workflow..."}
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
                <ChatInput
                  projectId={activeProjectId}
                  onRefreshRequest={handleRefreshRequest}
                  selectedTaskId={selectedTaskId}
                  addMessage={addMessage}
                />
              ) : (
                <div className="p-4 text-center text-muted-foreground">
                  {user ? "Select a project to begin." : "Loading chat or no project selected..."}
                </div>
              )}
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </ProtectedRoute>
  );
}


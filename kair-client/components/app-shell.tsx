'use client';

import { SidebarProvider } from '@/components/ui/sidebar';
import { HeaderBar } from '@/components/header-bar';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';
import { AuthProvider } from '@/context/auth-context';
import { ProjectTreePane } from '@/components/project-tree-pane';

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <SidebarProvider>
        <div className="flex min-h-0 flex-1 flex-col">
          <HeaderBar />
          <div className="flex-1 min-h-0">
            <PanelGroup direction="horizontal" className="h-full">
              <Panel defaultSize={22} minSize={12} maxSize={40}>
                <div className="h-full border-r">
                  <ProjectTreePane />
                </div>
              </Panel>
              <PanelResizeHandle className="w-1 bg-border hover:bg-muted-foreground/30 transition-colors cursor-col-resize" />
              <Panel defaultSize={78} minSize={40}>
                <div className="h-full overflow-hidden">{children}</div>
              </Panel>
            </PanelGroup>
          </div>
        </div>
      </SidebarProvider>
    </AuthProvider>
  );
}
/* eslint-disable @typescript-eslint/no-unused-vars */
"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import * as React from "react"
import {
  // IconHelp,
  // IconSearch,
  // IconSettings,
  IconAffiliate
} from "@tabler/icons-react"

import { NavSecondary } from "@/components/nav-secondary"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { cn } from "@/lib/utils";
import { useSecureFetch } from "@/hooks/useSecureFetch";
import { config } from "@/config";

type Project = { id: number; name: string };

const data = {
  user: {
    name: "kair-user",
    email: "kair-user@seas.upenn.edu",
    avatar: "/avatars/shadcn.jpg",
    organization: "AIRFoundry",
  },
  navSecondary: [
    // {
    //   title: "Settings",
    //   url: "#",
    //   icon: IconSettings,
    // },
    // {
    //   title: "Get Help",
    //   url: "mailto:zives@seas.upenn.edu",
    //   icon: IconHelp,
    // },
    // {
    //   title: "Search",
    //   url: "/retriever",
    //   icon: IconSearch,
    // },
  ],
}

export function AppSidebar({ className, ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const secureFetch = useSecureFetch();

  const [projects, setProjects] = React.useState<Project[]>([]);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [expanded, setExpanded] = React.useState<boolean>(true);

  // Fill current user info
  if (user) {
    data.user.email = user.email || data.user.email;
    data.user.name = user.name || data.user.name;
    data.user.avatar = user.avatar || data.user.avatar;
    data.user.organization = user.organization || "KAIR";
  }

  // Helper to extract selected project from /api/account
  const extractSelectedFromAccount = (acct: any): number | null => {
    const v =
      acct?.user?.profile?.descriptor?.selected_project_id ??
      acct?.user?.profile?.selected_project_id ??
      acct?.user?.selected_project_id ??
      acct?.user?.project_id ??
      null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  // Load projects + selected on mount
  React.useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const acctRes = await secureFetch(`${config.apiBaseUrl}/api/account`);
        if (!acctRes.ok) throw new Error(`account ${acctRes.status}`);
        const acct = await acctRes.json();
        if (!mounted) return;

        const sel = extractSelectedFromAccount(acct);
        setSelectedId(sel);

        // Prefer account projects; fallback to full list
        let list: Project[] = Array.isArray(acct?.user?.projects) ? acct.user.projects : [];
        if (!list.length) {
          const res = await secureFetch(`${config.apiBaseUrl}/api/projects/list?mine=1`);
          if (res.ok) {
            const j = await res.json();
            list = j?.projects || [];
          }
        }
        setProjects(list);
      } catch {
        // ignore
      }
    })();
    return () => { mounted = false; };
  }, [secureFetch]);

  // Listen for external project changes (from other components)
  React.useEffect(() => {
    const handler = (e: any) => {
      const pid = Number(e?.detail?.projectId);
      if (Number.isFinite(pid)) setSelectedId(pid);
    };
    window.addEventListener("project-changed", handler as any);
    return () => window.removeEventListener("project-changed", handler as any);
  }, []);

  const handleSelectProject = async (pid: number) => {
    if (!Number.isFinite(pid)) return;
    try {
      const res = await secureFetch(`${config.apiBaseUrl}/api/projects/select`, {
        method: "POST",
        body: JSON.stringify({ project_id: pid })
      });
      const j = await res.json();
      if (res.ok && j?.success) {
        setSelectedId(pid);

        // Update URL query (?projectId=...) preserving other params
        const params = new URLSearchParams(searchParams?.toString() || "");
        params.set("projectId", String(pid));
        router.replace(`${pathname}?${params.toString()}`);

        // Broadcast to other components
        window.dispatchEvent(new CustomEvent("project-changed", { detail: { projectId: pid } }));

        router.refresh(); // let server components react
      }
    } catch {
      // ignore
    }
  };

  return (
    <Sidebar collapsible {...props} className={cn("h-full", className)}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="data-[slot=sidebar-menu-button]:!p-1.5">
              <a href="#">
                <img src="/images/airfoundry-badge.png" alt="AIRFoundry logo" className="!size-8" />
                <span className="text-base font-semibold">KAIR Assistant</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        {/* Projects tree */}
        <div className="px-2 py-2">
          <button
            className="w-full text-left font-medium text-sm text-foreground/80 hover:text-foreground flex items-center gap-2"
            onClick={() => setExpanded(e => !e)}
            aria-expanded={expanded}
          >
            <IconAffiliate size={16} />
            <span>Projects</span>
            <span className="ml-auto text-xs">{expanded ? "▾" : "▸"}</span>
          </button>
          {expanded && (
            <ul className="mt-2 space-y-1">
              {projects.map(p => {
                const isActive = selectedId === p.id;
                return (
                  <li key={p.id}>
                    <button
                      className={cn(
                        "w-full text-left px-3 py-1.5 rounded-md text-sm",
                        isActive
                          ? "bg-primary/10 text-primary font-medium"
                          : "hover:bg-accent hover:text-accent-foreground"
                      )}
                      onClick={() => handleSelectProject(p.id)}
                      aria-current={isActive ? "page" : undefined}
                    >
                      {p.name}
                    </button>
                  </li>
                );
              })}
              {!projects.length && (
                <li className="text-xs text-muted-foreground px-3 py-1.5">No projects found</li>
              )}
            </ul>
          )}
        </div>

        {/* Keep secondary links at the bottom */}
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}

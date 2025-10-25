/* eslint-disable @typescript-eslint/no-unused-vars */
"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import * as React from "react"
import { IconAffiliate, IconHelp, IconSearch, IconSettings } from "@tabler/icons-react"
import { NavSecondary } from "@/components/nav-secondary"
import {
  Sidebar,
  SidebarContent,
  // SidebarRail, // optional, shows hover rail when collapsed
} from "@/components/ui/sidebar"
import { cn } from "@/lib/utils";
import { useSecureFetch } from "@/hooks/useSecureFetch";

type Project = { id: number; name: string };

// Define a more specific type for the account object
interface Account {
  user?: {
    project_id?: number | string;
    selected_project_id?: number | string;
    profile?: {
      selected_project_id?: number | string;
      descriptor?: {
        selected_project_id?: number | string;
      };
    };
    projects?: Project[];
  };
}

const data = {
  navSecondary: [
    { title: "Settings", url: "#", icon: IconSettings },
    { title: "Get Help", url: "mailto:zives@seas.upenn.edu", icon: IconHelp },
    { title: "Search", url: "/retriever", icon: IconSearch },
  ],
}

export function AppSidebar({ className, ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const secureFetch = useSecureFetch();

  const [projects, setProjects] = React.useState<Project[]>([]);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [expanded, setExpanded] = React.useState<boolean>(true);

  const extractSelectedFromAccount = (acct: Account | null): number | null => {
    const v =
      acct?.user?.profile?.descriptor?.selected_project_id ??
      acct?.user?.profile?.selected_project_id ??
      acct?.user?.selected_project_id ??
      acct?.user?.project_id ??
      null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  React.useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const acctRes = await secureFetch(`/api/account`);
        if (!acctRes.ok) throw new Error(`account ${acctRes.status}`);
        const acct = await acctRes.json();
        if (!mounted) return;

        const sel = extractSelectedFromAccount(acct);
        setSelectedId(sel);

        let list: Project[] = Array.isArray(acct?.user?.projects) ? acct.user.projects : [];
        if (!list.length) {
          const res = await secureFetch(`/api/projects/list?mine=1`);
          if (res.ok) {
            const j = await res.json();
            list = j?.projects || [];
          }
        }
        setProjects(list);
      } catch { /* noop */ }
    })();
    return () => { mounted = false; };
  }, [secureFetch]);

  React.useEffect(() => {
    const handler = (e: CustomEvent<{ projectId: number | null }>) => {
      const pid = e.detail?.projectId;
      if (pid !== undefined && Number.isFinite(pid)) {
        setSelectedId(pid);
      }
    };
    window.addEventListener("project-changed", handler as EventListener);
    return () => window.removeEventListener("project-changed", handler as EventListener);
  }, []);

  const handleSelectProject = async (pid: number) => {
    if (!Number.isFinite(pid)) return;
    try {
      const res = await secureFetch(`/api/projects/select`, {
        method: "POST",
        body: JSON.stringify({ project_id: pid })
      });
      const j = await res.json();
      if (res.ok && j?.success) {
        setSelectedId(pid);

        const params = new URLSearchParams(searchParams?.toString() || "");
        params.set("projectId", String(pid));
        router.replace(`${pathname}?${params.toString()}`);

        window.dispatchEvent(new CustomEvent("project-changed", { detail: { projectId: pid } }));
        router.refresh();
      }
    } catch { /* noop */ }
  };

  // Normalize collapsible; avoid boolean 'true'
  const { collapsible: collapsibleMode, ...restProps } = props;

  return (
    <Sidebar {...restProps} collapsible={collapsibleMode ?? "icon"} className={cn("h-full", className)}>
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

        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      {/* <SidebarRail /> */}
    </Sidebar>
  )
}

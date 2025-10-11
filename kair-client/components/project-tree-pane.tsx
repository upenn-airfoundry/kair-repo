'use client';

import * as React from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { IconChevronRight, IconChevronDown, IconFolder, IconFolderOpen, IconPlus } from '@tabler/icons-react';
import { cn } from '@/lib/utils';
import { useSecureFetch } from '@/hooks/useSecureFetch';
import { useAuth } from '@/context/auth-context';
import { config } from "@/config";
// NEW: UI components for dialog + form
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type Project = {
  id: number;
  name: string;
  // Optional hints for nesting if your API provides them
  parent_id?: number | null;
  path?: string | null; // e.g., "Org/Team/Project"
};

type TreeNode = {
  id: string;
  label: string;
  projectId?: number;
  children?: TreeNode[];
};

function buildTree(projects: Project[], groupLabel = "My Projects"): TreeNode[] {
  // Prefer parent_id hierarchy; fallback to path; else flat under "My Projects"
  const byId = new Map<number, Project>();
  const children: Record<number, Project[]> = {};
  let hasParentLink = false;

  for (const p of projects) {
    byId.set(p.id, p);
    if (p.parent_id != null && Number.isFinite(p.parent_id as number)) {
      hasParentLink = true;
      const pid = Number(p.parent_id);
      children[pid] ||= [];
      children[pid].push(p);
    }
  }

  const toNode = (p: Project): TreeNode => ({
    id: `p-${p.id}`,
    label: p.name,
    projectId: p.id,
    children: (children[p.id] || []).map(toNode),
  });

  if (hasParentLink) {
    // Roots: projects with no valid parent
    const roots = projects.filter(p => !(p.parent_id != null && byId.has(Number(p.parent_id))));
    return roots.map(toNode);
  }

  // Try path-based grouping
  const rootMap = new Map<string, TreeNode>();
  const ROOT_KEY = "__ROOT_GROUP__";
  for (const p of projects) {
    const path = (p.path || '').trim();
    if (path && path.includes('/')) {
      const parts = path.split('/').map(s => s.trim()).filter(Boolean);
      let level = rootMap;
      let parentNode: TreeNode | null = null;
      for (let i = 0; i < parts.length; i++) {
        const key = parts.slice(0, i + 1).join('/');
        let node = (i === 0 ? level.get(parts[i]) : (parentNode!.children || []).find(n => n.label === parts[i]));
        if (!node) {
          node = {
            id: `g-${key}`,
            label: parts[i],
            children: [],
          };
          if (i === 0) {
            level.set(parts[i], node);
          } else {
            parentNode!.children ||= [];
            parentNode!.children!.push(node);
          }
        }
        parentNode = node;
      }
      parentNode!.children ||= [];
      parentNode!.children!.push({ id: `p-${p.id}`, label: p.name, projectId: p.id, children: [] });
    } else {
      // Flat fallback under a single folder
      const group = rootMap.get(ROOT_KEY) || { id: 'g-root', label: groupLabel, children: [] as TreeNode[] };
      if (!rootMap.has(ROOT_KEY)) rootMap.set(ROOT_KEY, group);
      group.children!.push({ id: `p-${p.id}`, label: p.name, projectId: p.id, children: [] });
    }
  }
  return Array.from(rootMap.values());
}

export function ProjectTreePane() {
  const secureFetch = useSecureFetch();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const makePossessive = (name: string) => {
    const n = (name || "").trim();
    if (!n) return "My Projects";
    return n.endsWith("s") || n.endsWith("S") ? `${n}' Projects` : `${n}'s Projects`;
  };
  const groupLabel = makePossessive(user?.name || "");
  const isLogin = pathname?.startsWith('/login');

  const [projects, setProjects] = React.useState<Project[]>([]);
  const [tree, setTree] = React.useState<TreeNode[]>([]);
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const reqSeq = React.useRef(0);

  // NEW: create project dialog state
  const [createOpen, setCreateOpen] = React.useState(false);
  const [createName, setCreateName] = React.useState('');
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const toggle = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSelectProject = async (pid: number) => {
    if (!Number.isFinite(pid)) return;
    try {
      const res = await secureFetch(`${config.apiBaseUrl}/api/projects/select`, {
        method: 'POST',
        body: JSON.stringify({ project_id: pid }),
      });
      const j = await res.json();
      if (res.ok && j?.success) {
        setSelectedId(pid);
        // Update URL (?projectId=...)
        const params = new URLSearchParams(searchParams?.toString() || '');
        params.set('projectId', String(pid));
        router.replace(`${pathname}?${params.toString()}`);

        // Notify other panes
        window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: pid } }));
        router.refresh();
      }
    } catch {
      // ignore
    }
  };

  const loadProjects = React.useCallback(async () => {
    // Do not fetch on the login page
    if (isLogin) return;
    const mySeq = ++reqSeq.current;
    try {
      const acctRes = await secureFetch(`${config.apiBaseUrl}/api/account`);
      const acct = acctRes.ok ? await acctRes.json() : null;
      if (mySeq !== reqSeq.current) return;

      const sel = Number(
        acct?.user?.profile?.descriptor?.selected_project_id ??
          acct?.user?.profile?.selected_project_id ??
          acct?.user?.selected_project_id ??
          acct?.user?.project_id ??
          NaN
      );
      setSelectedId(Number.isFinite(sel) ? sel : null);

      let list: Project[] = Array.isArray(acct?.user?.projects) ? acct.user.projects : [];
      if (!list.length) {
        const res = await secureFetch(`${config.apiBaseUrl}/api/projects/list?mine=1`);
        if (res.ok) {
          const j = await res.json();
          list = j?.projects || [];
        }
      }
      setProjects(list);
      const newTree = buildTree(list, groupLabel);
      setTree(newTree);

      // Expand top-level nodes by default
      const topIds = new Set<string>();
      for (const n of newTree) topIds.add(n.id);
      setExpanded(topIds);
    } catch {
      // ignore
    }
  }, [secureFetch, groupLabel, isLogin]);

  // Initial load
  React.useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Refresh immediately when login state changes
  React.useEffect(() => {
    if (user) {
      loadProjects();
    }
  }, [user?.id, user?.email, loadProjects]);

  // When on /login, clear the tree immediately
  React.useEffect(() => {
    if (isLogin) {
      setProjects([]);
      setTree([]);
      setSelectedId(null);
      setExpanded(new Set());
    }
  }, [isLogin]);

  React.useEffect(() => {
    const handler = (e: any) => {
      const pid = Number(e?.detail?.projectId);
      if (Number.isFinite(pid)) setSelectedId(pid);
    };
    window.addEventListener('project-changed', handler as any);
    return () => window.removeEventListener('project-changed', handler as any);
  }, []);

  // NEW: create project submit
  const onCreateProject = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!createName.trim()) {
      setCreateError('Please enter a project name.');
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      // Try to mirror ProjectGraphPane’s API; adjust if your backend expects different payload
      const res = await secureFetch(`${config.apiBaseUrl}/api/projects/create`, {
        method: 'POST',
        body: JSON.stringify({ name: createName.trim() }),
      });
      const j = await res.json();
      if (!res.ok || (!j?.success && !j?.project && !j?.id && !j?.project_id)) {
        throw new Error(j?.error || 'Failed to create project');
      }
      const newId: number =
        Number(j?.project?.id) ||
        Number(j?.id) ||
        Number(j?.project_id);

      // Close dialog + clear input
      setCreateOpen(false);
      setCreateName('');

      // Reload tree, then select the new project (which triggers all panes)
      await loadProjects();
      if (Number.isFinite(newId)) {
        await handleSelectProject(newId);
      }
    } catch (err: any) {
      setCreateError(err?.message || 'Error creating project');
    } finally {
      setCreating(false);
    }
  };

  const renderNode = (node: TreeNode, depth = 0): React.ReactNode => {
    const isLeaf = !node.children || node.children.length === 0;
    const isOpen = expanded.has(node.id);
    const isSelected = node.projectId != null && selectedId === node.projectId;

    return (
      <li key={node.id}>
        <div
          className={cn(
            "flex items-center gap-1 pr-2 py-1.5 rounded-md cursor-pointer transition-all",
            "text-foreground/90",
            "hover:bg-muted",
            // Selected: light gray bg + bold dark outline (matches graph)
            isSelected && "bg-muted ring-2 ring-foreground/80 text-foreground font-semibold shadow-sm"
          )}
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => {
            if (isLeaf) {
              if (node.projectId != null) handleSelectProject(node.projectId);
            } else {
              toggle(node.id);
            }
          }}
        >
          {!isLeaf ? (
            <>
              <span className="text-muted-foreground">
                {isOpen ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}
              </span>
              <span className="text-muted-foreground">{isOpen ? <IconFolderOpen size={16} /> : <IconFolder size={16} />}</span>
              <span className="ml-1">{node.label}</span>
            </>
          ) : (
            <>
              <span className="inline-block w-4 opacity-50" />
              <span className="text-muted-foreground">
                <IconFolder size={16} />
              </span>
              <span className="ml-1">{node.label}</span>
            </>
          )}
        </div>
        {!isLeaf && isOpen && node.children && node.children.length > 0 && (
          <ul className="mt-0">{node.children.map(child => renderNode(child, depth + 1))}</ul>
        )}
      </li>
    );
  };

  return (
    <div className="h-full w-full p-2 overflow-hidden">
      <div className="h-full w-full overflow-auto rounded-lg border bg-muted/30 shadow-inner">
        <div className="sticky top-0 z-10 px-3 py-2 bg-muted/40 backdrop-blur border-b flex items-center">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Projects</div>
          {!isLogin && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="ml-auto h-7 px-2 text-xs"
              onClick={() => {
                setCreateError(null);
                setCreateName('');
                setCreateOpen(true);
              }}
              aria-label="Create new project"
              title="Create new project"
            >
              <IconPlus size={16} />
              <span className="sr-only">Create project</span>
            </Button>
          )}
        </div>
        <div className="px-2 py-2">
          <ul className="space-y-1">{!isLogin && tree.map(n => renderNode(n))}</ul>
          {!isLogin && !projects.length && (
            <div className="text-xs text-muted-foreground px-2 py-2">No projects found</div>
          )}
          {isLogin && (
            <div className="text-xs text-muted-foreground px-2 py-2">Please log in to view projects</div>
          )}
        </div>
      </div>

      {/* Create Project Dialog */}
      <Dialog open={createOpen && !isLogin} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create new project</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={onCreateProject}
            className="grid gap-3"
          >
            <div className="grid gap-1.5">
              <Label htmlFor="project-name">Project name</Label>
              <Input
                id="project-name"
                autoFocus
                placeholder="e.g., My Research Project"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                disabled={creating}
              />
            </div>
            {createError && (
              <div className="text-xs text-red-600">{createError}</div>
            )}
            <DialogFooter className="mt-1">
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateOpen(false)}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={creating || !createName.trim()}>
                {creating ? "Creating..." : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

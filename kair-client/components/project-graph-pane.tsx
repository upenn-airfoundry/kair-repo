"use client";

import React, { useEffect, useMemo, useState, useCallback } from "react"; // include useCallback here
import { useRouter, usePathname } from "next/navigation";
import { useSecureFetch } from "@/hooks/useSecureFetch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ReactFlow, {
  Controls,
  Background,
  applyNodeChanges,
  applyEdgeChanges,
  Node,
  Edge,
  OnNodesChange,
  OnEdgesChange,
  MarkerType,
  Position,
  SimpleBezierEdge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { config } from "@/config";
import DetailsViewer from './details-viewer';
import dagre from 'dagre';
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";

// Remove the duplicate hooks import
// import { useState, useEffect, useCallback } from 'react';

// Define specific types for the data being fetched
interface Task {
  id: number | string;
  name: string;
  schema: string;
}

interface Dependency {
  source: number | string;
  target: number | string;
  data_flow: string;
  relationship_description: string;
  data_schema: string;
}

// Add missing Project type
type Project = { id: number; name: string; description?: string };

// Sentinel for create-new option
const CREATE_SENTINEL = "__create__";

// Extend props to include onProjectChanged (used below)
interface ProjectGraphPaneProps {
  projectId: number;
  projectName: string;
  refreshKey: number;
  onProjectChanged?: (projectId: number) => void;
}

const nodeWidth = 180;
const nodeHeight = 55; // Approximate height of a node

const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'LR') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.targetPosition = Position.Left;
    node.sourcePosition = Position.Right;
    // We are shifting the dagre node position (anchor=center) to the top left
    // so it matches the React Flow node anchor point (top left).
    node.position = {
      x: nodeWithPosition.x - nodeWidth / 2,
      y: nodeWithPosition.y - nodeHeight / 2,
    };
  });

  return { layoutedNodes: nodes, layoutedEdges: edges };
};

// add small helpers at top-level inside the module
const dedupeById = (arr: Project[]) => {
  const seen = new Set<number>();
  return arr.filter(p => (seen.has(p.id) ? false : (seen.add(p.id), true)));
};

// Extract selected project id from account payload (checks descriptor, then profile, then top-level)
const extractSelectedProjectId = (acct: any): number | null => {
  const v =
    acct?.user?.profile?.descriptor?.selected_project_id ??
    acct?.user?.profile?.selected_project_id ??
    acct?.user?.selected_project_id ??
    acct?.user?.project_id ??
    null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export default function ProjectGraphPane({ projectId, projectName, refreshKey, onProjectChanged }: ProjectGraphPaneProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedElement, setSelectedElement] = useState<Node | Edge | null>(null);
  const secureFetch = useSecureFetch();
  const router = useRouter();
  const pathname = usePathname();

  // MOVE THESE STATE HOOKS ABOVE ANY EFFECTS THAT USE selectedId
  const [userName, setUserName] = useState<string>("");
  const [org, setOrg] = useState<string>("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [accountSelectedId, setAccountSelectedId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");

  const onNodesChange: OnNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), [setNodes]);
  const onEdgesChange: OnEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), [setEdges]);

  // Use selectedId (fallback to prop) to drive graph fetching
  useEffect(() => {
    const pid = selectedId ?? projectId;
    if (!pid) return;

    const fetchData = async () => {
      try {
        const [tasksRes, depsRes] = await Promise.all([
          secureFetch(`${config.apiBaseUrl}/api/project/${pid}/tasks`),
          secureFetch(`${config.apiBaseUrl}/api/project/${pid}/dependencies`)
        ]);
        const tasksData = await tasksRes.json();
        const depsData = await depsRes.json();

        const initialNodes: Node[] = tasksData.tasks.map((task: Task) => ({
          id: task.id.toString(),
          position: { x: 0, y: 0 },
          data: { label: task.name, schema: task.schema },
          style: {
            backgroundColor: '#F0F4FA',
            border: '1px solid #011F5B',
            borderRadius: 8,
            padding: '10px 15px',
            fontSize: '12px',
            width: nodeWidth,
            color: '#011F5B',
          },
        }));

        const initialEdges: Edge[] = depsData.dependencies.map((dep: Dependency) => {
          const baseStyle = { stroke: '#333', strokeWidth: 1.5 };
          let edgeStyle = { ...baseStyle };
          let markerStart;

          if (dep.data_flow === 'rethinking the previous task') edgeStyle = { ...edgeStyle, strokeDasharray: '5,5' };
          if (dep.data_flow === 'gated by user feedback') markerStart = { type: MarkerType.ArrowClosed, color: '#333', width: 15, height: 15 };

          return {
            id: `e${dep.source}-${dep.target}`,
            source: dep.source.toString(),
            target: dep.target.toString(),
            type: 'simplebezier',
            markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20, color: '#333' },
            markerStart,
            style: edgeStyle,
            data: dep,
          };
        });

        const { layoutedNodes, layoutedEdges } = getLayoutedElements(initialNodes, initialEdges);
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
      } catch (error) {
        console.error("Failed to fetch project graph data:", error);
      }
    };

    fetchData();
  }, [selectedId, projectId, refreshKey, secureFetch]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => setSelectedElement(node);
  const onEdgeClick = (_: React.MouseEvent, edge: Edge) => setSelectedElement(edge);

  // Ensure the combo box has an entry for the current project from props
  useEffect(() => {
    if (!projectId || !projectName) return;
    setProjects(prev => {
      const merged = [{ id: projectId, name: projectName }, ...prev];
      return dedupeById(merged);
    });
    setSelectedId(projectId);
  }, [projectId, projectName]);

  // Select the current project immediately (don’t wait for list fetch)
  useEffect(() => {
    if (projectId) setSelectedId(projectId);
  }, [projectId]);

  // Load account info and projects (use API base + credentials)
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const acctRes = await secureFetch(`${config.apiBaseUrl}/api/account`);
        if (!acctRes.ok) throw new Error(`account ${acctRes.status}`);
        const acct = await acctRes.json();
        if (!mounted) return;

        setUserName(acct?.user?.name || "");
        setOrg(acct?.user?.profile?.organization || acct?.user?.organization || "");

        // Capture selected from account and keep in state for syncing
        const acctSel = extractSelectedProjectId(acct);
        setAccountSelectedId(acctSel);

        // Prefer projects from account; fallback to full list for this user
        let projList: Project[] = Array.isArray(acct?.user?.projects) ? acct.user.projects : [];

        const projectsRes = await secureFetch(`${config.apiBaseUrl}/api/projects/list?mine=1`);
        if (projectsRes.ok) {
          const projJson = await projectsRes.json();
          projList = projJson?.projects || projList;
        }

        // Merge with the current prop project
        const merged = dedupeById(
          (projectId && projectName && !projList.some(p => p.id === projectId))
            ? [{ id: projectId, name: projectName }, ...projList]
            : projList
        );
        setProjects(merged);

        // Prefer prop projectId, then account selection, then first project
        const preferProp = projectId && merged.some(p => p.id === projectId) ? projectId : null;
        const preferAcct = acctSel && merged.some(p => p.id === acctSel) ? acctSel : null;
        const pref = preferProp ?? preferAcct ?? (merged[0]?.id ?? null);
        setSelectedId(pref ?? null);
      } catch {
        // Leave seeded project as-is on error
      }
    })();
    return () => { mounted = false; };
  }, [secureFetch, projectId, projectName]);

  // Keep selectedId synced to account-selected id when it changes (and exists in list)
  useEffect(() => {
    if (accountSelectedId && projects.some(p => p.id === accountSelectedId)) {
      setSelectedId(prev => (prev === accountSelectedId ? prev : accountSelectedId));
    }
  }, [accountSelectedId, projects]);

  const displayRight = useMemo(() => {
    const right = [userName, org].filter(Boolean).join(" at ");
    return right ? ` - ${right}` : "";
  }, [userName, org]);

  // After selecting a project, persist and refetch full list
  const onSelectChange = async (val: string) => {
    if (val === CREATE_SENTINEL) { setCreateOpen(true); return; }
    const id = parseInt(val, 10);
    if (!Number.isFinite(id)) return;
    try {
      const res = await secureFetch(`${config.apiBaseUrl}/api/projects/select`, {
        method: "POST",
        body: JSON.stringify({ project_id: id })
      });
      const j = await res.json();
      if (j?.success) {
        // Update local selection immediately
        setSelectedId(id);

        // Update URL query so server components/pages can react (eg. chat)
        const params = new URLSearchParams(window.location.search);
        params.set('projectId', String(id));
        router.replace(`${pathname}?${params.toString()}`);

        // Notify other client components (optional)
        window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: id } }));

        // Refetch account to sync selected project id
        try {
          const acctRes = await secureFetch(`${config.apiBaseUrl}/api/account`);
          if (acctRes.ok) {
            const acct = await acctRes.json();
            const sid = extractSelectedProjectId(acct);
            setAccountSelectedId(sid);
          }
        } catch {}

        // Refetch full project list
        const projectsRes = await secureFetch(`${config.apiBaseUrl}/api/projects/list?mine=1`);
        if (projectsRes.ok) {
          const projJson = await projectsRes.json();
          setProjects(prev => dedupeById([...(projJson?.projects || []), ...prev]));
        }

        onProjectChanged?.(id);
        router.refresh();
      }
    } catch { /* ignore */ }
  };

  // After creating a project, refetch and select it
  const onCreateConfirm = async () => {
    if (!newProjName.trim()) return;
    try {
      const res = await secureFetch(`${config.apiBaseUrl}/api/projects/create`, {
        method: "POST",
        body: JSON.stringify({ name: newProjName.trim(), description: "" })
      });
      const j = await res.json();
      const newId = j?.project_id as number | undefined;
      if (newId) {
        // Merge into list
        const projectsRes = await secureFetch(`${config.apiBaseUrl}/api/projects/list?mine=1`);
        if (projectsRes.ok) {
          const projJson = await projectsRes.json();
          setProjects(dedupeById([{ id: newId, name: newProjName.trim() }, ...(projJson?.projects || [])]));
        } else {
          setProjects(prev => dedupeById([{ id: newId, name: newProjName.trim() }, ...prev]));
        }

        // Select new project
        setSelectedId(newId);
        setAccountSelectedId(newId);

        // Update URL and notify
        const params = new URLSearchParams(window.location.search);
        params.set('projectId', String(newId));
        router.replace(`${pathname}?${params.toString()}`);
        window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: newId } }));

        setCreateOpen(false);
        setNewProjName("");
        onProjectChanged?.(newId);
        router.refresh();
      }
    } catch { /* ignore */ }
  };
  // Rename this derived variable to avoid clashing with prop `projectName`
  const selectedProjectName = useMemo(() => {
    return projects.find(p => p.id === selectedId)?.name || "Select project";
  }, [projects, selectedId]);

  // Memoize edgeTypes so identity stays stable across renders/HMR
  const edgeTypes = useMemo(() => ({ simplebezier: SimpleBezierEdge }), []);

  // Clear details pane on project change
  React.useEffect(() => {
    // This effect runs whenever the active project changes (selectedId preferred, fallback projectId)
    // Clear any node/edge selection to avoid stale details
    setSelectedElement(null);
  }, [selectedId, projectId]);

  // Also listen to external changes (sidebar) and sync selection
  React.useEffect(() => {
    const handler = (e: any) => {
      const pid = Number(e?.detail?.projectId);
      if (Number.isFinite(pid)) {
        setSelectedId(pid);
      }
    };
    window.addEventListener("project-changed", handler as any);
    return () => window.removeEventListener("project-changed", handler as any);
  }, []);

  // Handle selection changes from React Flow (syncs details pane and supports clearing)
  const onSelectionChange = useCallback((params: { nodes: Node[]; edges: Edge[] }) => {
    if (params?.nodes?.length) {
      setSelectedElement(params.nodes[0]);
      return;
    }
    if (params?.edges?.length) {
      setSelectedElement(params.edges[0]);
      return;
    }
    setSelectedElement(null);
  }, []);

  // Clicking the background (pane) clears selection and details
  const onPaneClick = useCallback(() => {
    setSelectedElement(null);
  }, []);

  return (
    <div className="h-full w-full border rounded-lg flex flex-col">
      {/* Selection highlight styles */}
      <style jsx global>{`
        /* Make selected task nodes stand out */
        .react-flow__node.selected {
          border: 2px solid #0b5fff !important;
          background-color: #e6f0ff !important;
          box-shadow: 0 0 0 2px rgba(11, 95, 255, 0.12);
        }
      `}</style>

      <div className="flex items-center justify-between gap-3 p-2 border-b">
        <div className="flex items-center gap-2">
          <Select value={selectedId?.toString() ?? ""} onValueChange={onSelectChange}>
            <SelectTrigger className="w-[280px]">
              <SelectValue placeholder="Select project" />
            </SelectTrigger>
            <SelectContent>
              {projects.map(p => (
                <SelectItem key={p.id} value={p.id.toString()}>{p.name}</SelectItem>
              ))}
              <div className="border-t my-1" />
              <SelectItem value={CREATE_SENTINEL}>+ Create new project</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-sm text-muted-foreground">{` ${displayRight}`}</span>
        </div>

        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create new project</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <Input
                placeholder="Project name"
                value={newProjName}
                onChange={e => setNewProjName(e.target.value)}
              />
            </div>
            <DialogFooter>
              <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button onClick={onCreateConfirm}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      <PanelGroup direction="horizontal" className="flex-1 min-h-0">
        <Panel defaultSize={66} minSize={30}>
          <div className="h-full w-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
              onSelectionChange={onSelectionChange}  // NEW: keep details in sync with selection
              onPaneClick={onPaneClick}              // NEW: click background to unselect and clear details
              edgeTypes={edgeTypes}
              fitView
              minZoom={0.2}
            >
              <Controls />
              <Background />
            </ReactFlow>
          </div>
        </Panel>
        <PanelResizeHandle className="w-2 flex items-center justify-center bg-muted transition-colors hover:bg-muted-foreground/20">
          <div className="h-8 w-1 rounded-full bg-border" />
        </PanelResizeHandle>
        <Panel defaultSize={34} minSize={20}>
          <div className="h-full w-full flex flex-col">
            <DetailsViewer selectedElement={selectedElement} />
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
"use client";

import React, { useEffect, useMemo, useState, useCallback, useRef } from "react";
import type { CSSProperties } from "react";
import { useSecureFetch } from "@/hooks/useSecureFetch";
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
  StepEdge,
  StraightEdge,
  Handle,
  type NodeProps,
  ReactFlowInstance,
  type EdgeMarker,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { config } from "@/config";
import DetailsViewer from './details-viewer';
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import { createPortal } from 'react-dom';

// dagre not used with current layout

type TaskNodeData = {
  label: string;
  schema: string;
  openMenuAt?: (clientX: number, clientY: number) => void;
};

// Custom node with 4 handles so we can connect dataflow (L/R) and parent-child (T/B) separately
function TaskNode({ data }: NodeProps<TaskNodeData>) {
  return (
    <div
      onContextMenu={(e) => {
        if (data?.openMenuAt) {
          e.preventDefault();
          e.stopPropagation();
          data.openMenuAt(e.clientX, e.clientY);
        }
      }}
    >
      {/* Top/Bottom for parent-subtask edges */}
      <Handle id="top" type="target" position={Position.Top} />
      <Handle id="bottom" type="source" position={Position.Bottom} />
      {/* Left/Right for dataflow edges */}
      <Handle id="left" type="target" position={Position.Left} />
      <Handle id="right" type="source" position={Position.Right} />
     <div>{data?.label}</div>
    </div>
  );
}

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

// Extend props to include onProjectChanged (used below)
export interface ProjectGraphPaneProps {
  projectId: number;
  projectName: string;
  refreshKey: number;
  onProjectChanged?: (projectId: number) => void;
  onTaskSelected?: (taskId: number | null) => void;
}

const nodeWidth = 180;
const nodeHeight = 55; // Approximate height of a node
const rowGap = 120;     // Minimum vertical gap between nodes
const colGap = 40;     // Minimum horizontal padding within a slice

// Topological levels along parent-subtask edges, returning level per node and max level
function computeTopoLevels(nodes: Node[], deps: Dependency[]): { levelOf: Map<string, number>; maxLevel: number } {
  const ids = nodes.map(n => n.id.toString());
  const idSet = new Set(ids);
  const parentEdges = deps.filter(d => d.data_flow === 'parent task-subtask');

  const adj = new Map<string, string[]>();
  const indeg = new Map<string, number>();
  for (const id of ids) {
    adj.set(id, []);
    indeg.set(id, 0);
  }
  for (const e of parentEdges) {
    const s = e.source.toString();
    const t = e.target.toString();
    if (!idSet.has(s) || !idSet.has(t)) continue;
    adj.get(s)!.push(t);
    indeg.set(t, (indeg.get(t) ?? 0) + 1);
  }

  const levelOf = new Map<string, number>();
  const q: string[] = [];
  for (const id of ids) {
    if ((indeg.get(id) ?? 0) === 0) {
      levelOf.set(id, 0);
      q.push(id);
    }
  }
  // If cycle or no roots, default all to level 0
  if (q.length === 0) {
    for (const id of ids) levelOf.set(id, 0);
    return { levelOf, maxLevel: 0 };
  }

  let maxLevel = 0;
  while (q.length) {
    const u = q.shift()!;
    const uLevel = levelOf.get(u) ?? 0;
    for (const v of adj.get(u) ?? []) {
      // Assign level as max parent level + 1
      const next = Math.max((levelOf.get(v) ?? 0), uLevel + 1);
      levelOf.set(v, next);
      maxLevel = Math.max(maxLevel, next);
      indeg.set(v, (indeg.get(v) ?? 1) - 1);
      if ((indeg.get(v) ?? 0) === 0) q.push(v);
    }
  }

  // Ensure every node has a level
  for (const id of ids) {
    if (!levelOf.has(id)) levelOf.set(id, 0);
  }
  return { levelOf, maxLevel };
}

const getLayoutedElements = (
  nodes: Node<TaskNodeData>[],
  allEdges: Edge<Dependency>[],
  deps: Dependency[],
  viewportWidth: number,
  viewportHeight: number
) => {
  const width = viewportWidth > 0 ? viewportWidth : 1000;
  const height = viewportHeight > 0 ? viewportHeight : 700;

  // Compute topo levels from parent-subtask edges
  const { levelOf, maxLevel } = computeTopoLevels(nodes, deps);
  const levelCount = Math.max(1, maxLevel + 1);

  // Each level gets a horizontal band (slice) of the viewport's vertical space
  const sliceHeight = Math.max(nodeHeight + rowGap, Math.floor(height / levelCount));
  const sidePad = 20; // horizontal padding inside each row
  const bandTopPad = 10; // vertical padding inside each band

  // Group nodes by level and sort by lexicographical order of labels
  const levelBuckets = new Map<number, Node<TaskNodeData>[]>();
  for (const n of nodes) {
    const lvl = levelOf.get(n.id.toString()) ?? 0;
    if (!levelBuckets.has(lvl)) levelBuckets.set(lvl, []);
    levelBuckets.get(lvl)!.push(n);
  }
  for (const arr of levelBuckets.values()) {
    arr.sort((a, b) => {
      const la = String(a.data?.label ?? '');
      const lb = String(b.data?.label ?? '');
      return la.localeCompare(lb, undefined, { sensitivity: 'base' });
    });
  }

  // Position nodes: each level in its own horizontal band, nodes laid out left-to-right
  for (let lvl = 0; lvl < levelCount; lvl++) {
    const arr = levelBuckets.get(lvl) ?? [];
    const count = Math.max(1, arr.length);
    const usableWidth = Math.max(nodeWidth + colGap, width - sidePad * 2);
    const stepX = Math.max(nodeWidth + colGap, Math.floor(usableWidth / count));
    const bandTop = lvl * sliceHeight;
    const y = Math.floor(bandTop + bandTopPad + (sliceHeight - bandTopPad * 2 - nodeHeight) / 2);

    arr.forEach((node, idx) => {
      const x = sidePad + idx * stepX;
      node.targetPosition = Position.Left;  // for dataflow edges
      node.sourcePosition = Position.Right; // for dataflow edges
      node.position = { x, y };
    });
  }

  return { layoutedNodes: nodes, layoutedEdges: allEdges };
};

// Helper: remove "Task X:" and "Plan:" prefixes for display
function stripTaskLabel(name: string): string {
  if (!name) return "";
  return name
    // .replace(/^Task\s*\d+\s*:\s*/i, "")
    .replace(/^Task\s*/i, "")
    .replace(/^Plan:\s*/i, "-")
    .trim();
}

// Helper: choose a subtle background color based on task intent keywords
function backgroundForTask(name: string): string | undefined {
  if (!name) return undefined;
  const s = name.toLowerCase();

  // (a) plan
  if (/.*\bplan(ning)?\b/.test(s)) {
    // light gray
    return "hsla(0, 0%, 92%, 0.9)";
  }
  // (b) gather or collect
  if (/.*\b(gather|collect|summarize)\b/.test(s)) {
    // light green
    return "hsla(140, 60%, 92%, 0.9)";
  }
  // (c) identify or select
  if (/.*\b(identify|select|choose)\b/.test(s)) {
    // light yellow
    return "hsla(50, 100%, 90%, 0.9)";
  }
  // (d) consolidate or develop
  if (/.*\b(consolidate|develop|design)\b/.test(s)) {
    // light red
    return "hsla(0, 80%, 94%, 0.9)";
  }

  return undefined;
}

export default function ProjectGraphPane({ projectId, projectName, refreshKey, onTaskSelected }: ProjectGraphPaneProps) {
  const [nodes, setNodes] = useState<Node<TaskNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge<Dependency>[]>([]);
  const [selectedElement, setSelectedElement] = useState<Node | Edge | null>(null);
  const secureFetch = useSecureFetch();
  const rfInstance = useRef<ReactFlowInstance | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const nodeTypes = useMemo(() => ({ task: TaskNode }), []);
  const [localRefreshTick, setLocalRefreshTick] = useState(0);
  const preserveSelectedIdRef = useRef<string | null>(null);

  // Context menu state
  const [menu, setMenu] = useState<{ visible: boolean; x: number; y: number; nodeId: string | null }>({
    visible: false, x: 0, y: 0, nodeId: null,
  });
  const menuRef = useRef<HTMLDivElement | null>(null);
  const MENU_W = 224;
  const MENU_H = 96;

  // Open the menu at viewport coordinates using a portal
  const openMenuAt = useCallback((clientX: number, clientY: number, nodeId?: string) => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const x = Math.max(4, Math.min(clientX, vw - MENU_W - 4));
    const y = Math.max(4, Math.min(clientY, vh - MENU_H - 4));
    setMenu({ visible: true, x, y, nodeId: nodeId ?? menu.nodeId });
  }, [MENU_W, MENU_H, menu.nodeId]);

  // Track container size for viewport-aware layout
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setContainerSize({ width: r.width, height: r.height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Base graph data (unlayouted) so we can re-layout on resize
  const [baseNodes, setBaseNodes] = useState<Node[]>([]);
  const [baseEdges, setBaseEdges] = useState<Edge[]>([]);
  const [baseDeps, setBaseDeps] = useState<Dependency[]>([]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );
  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

   // Keep resetViewport simple; don't depend on nodes.length so it doesn't capture stale values
   const resetViewport = useCallback(() => {
     const inst = rfInstance.current;
     if (!inst) return;
     try {
       inst.setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 120 });
       inst.fitView({
         padding: 0.2,
         includeHiddenNodes: true,
         maxZoom: 1.25,
         duration: 300,
       });
     } catch {
       /* no-op */
     }
   }, []);

   // Use selectedId (fallback to prop) to drive graph fetching (no layout here)
   useEffect(() => {
     const pid = selectedId ?? projectId;
     if (!pid) return;
     (async () => {
       try {
         const [tasksRes, depsRes] = await Promise.all([
           secureFetch(`${config.apiBaseUrl}/api/project/${pid}/tasks`, { cache: "no-store" }),
           secureFetch(`${config.apiBaseUrl}/api/project/${pid}/dependencies`, { cache: "no-store" }),
         ]);
         const tasksData = await tasksRes.json();
         const depsData = await depsRes.json();

         const initialNodes: Node<TaskNodeData>[] = tasksData.tasks.map((task: Task) => {
           const label = stripTaskLabel(task.name);
           const bg = backgroundForTask(task.name);
           return {
             id: task.id.toString(),
             position: { x: 0, y: 0 },
             data: {
               label,
               schema: task.schema,
               openMenuAt: (clientX: number, clientY: number) => openMenuAt(clientX, clientY, task.id.toString()),
             },
             className: "task-node",
             type: "task",
             style: { width: nodeWidth, ...(bg ? { backgroundColor: bg } : {}) },
           };
         });

         const initialEdges: Edge<Dependency>[] = depsData.dependencies.map((dep: Dependency) => {
           const baseStyle: CSSProperties = { stroke: '#333', strokeWidth: 1.5 };
           const edgeStyle: CSSProperties = { ...baseStyle };
           let markerStart: EdgeMarker | undefined;

           if (dep.data_flow === 'rethinking the previous task') {
             edgeStyle.strokeDasharray = '5,5';
           }
           // Hide feedback edges (invisible/non-interactive)
           const isFeedback = dep.data_flow === 'gated by user feedback';

           const isParent = dep.data_flow === 'parent task-subtask';
           if (isParent) {
             // Dotted straight line for parent-child edges
             edgeStyle.strokeDasharray = '4 4';
           }
           return {
             id: `e${dep.source}-${dep.target}`,
             source: dep.source.toString(),
             target: dep.target.toString(),
             type: isParent ? 'straight' : 'simplebezier',
             hidden: isFeedback,
             markerEnd: isFeedback ? undefined : { type: MarkerType.ArrowClosed, width: 20, height: 20, color: '#333' },
             markerStart: isFeedback ? undefined : markerStart,
             style: isFeedback ? { ...edgeStyle, opacity: 0, pointerEvents: 'none' } : edgeStyle,
             // Route via specific handles
             sourceHandle: isParent ? 'bottom' : 'right',
             targetHandle: isParent ? 'top' : 'left',
             data: dep,
           };
         });

         setBaseNodes(initialNodes);
         setBaseEdges(initialEdges);
         setBaseDeps(depsData.dependencies);
       } catch (error) {
         console.error("Failed to fetch project graph data:", error);
       }
     })();
   }, [selectedId, projectId, refreshKey, localRefreshTick, secureFetch, openMenuAt]);

   // Re-layout on container resize with the stored base graph (guard 0-size)
   useEffect(() => {
     if (!baseNodes.length) return;
     if (containerSize.width <= 0 || containerSize.height <= 0) return;
     const nodesClone = baseNodes.map(n => ({ ...n, position: { x: 0, y: 0 } }));
     const { layoutedNodes, layoutedEdges } =
      getLayoutedElements(nodesClone, baseEdges, baseDeps, containerSize.width, containerSize.height);
     setNodes(layoutedNodes);
     setEdges(layoutedEdges);
   }, [containerSize.width, containerSize.height, baseNodes, baseEdges, baseDeps]);

   // Fit/center after nodes/edges update (only when we have size and nodes)
   useEffect(() => {
     if (!rfInstance.current) return;
     // wait a tick so ReactFlow has measured nodes
     const id = requestAnimationFrame(() => resetViewport());
     return () => cancelAnimationFrame(id);
   }, [selectedId, projectId, nodes.length, edges.length, resetViewport]);

   // After we refresh nodes, restore selection to the preserved node ID (if any)
   useEffect(() => {
     if (!preserveSelectedIdRef.current || nodes.length === 0) return;
     const wanted = preserveSelectedIdRef.current;
     const found = nodes.find(n => n.id.toString() === wanted);
     if (found) {
       setSelectedElement(found);
       const n = Number(found.id);
       if (Number.isFinite(n)) {
         if (onTaskSelected) onTaskSelected(n);
       }
     }
     preserveSelectedIdRef.current = null;
   }, [nodes, onTaskSelected]);

   // Flesh-out helper: calls backend and triggers local refresh; keeps selection
   const fleshOutTask = useCallback(async (taskId: string) => {
     try {
       preserveSelectedIdRef.current = taskId;
       const resp = await secureFetch(`${config.apiBaseUrl}/api/task/${taskId}/flesh_out`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         credentials: 'include',
         body: JSON.stringify({})
       });
       if (!resp.ok) {
         const txt = await resp.text().catch(() => "");
         console.error("Flesh-out failed:", txt);
         return;
       }
       setLocalRefreshTick(v => v + 1);
     } catch (e) {
       console.error("Flesh-out error:", e);
     }
   }, [secureFetch]);

   const renameTask = useCallback(async (taskId: string) => {
     const current = nodes.find((n) => n.id.toString() === taskId);
     const existing = String(current?.data?.label ?? '');
     const name = window.prompt("Rename task to:", existing);
     if (!name || name.trim() === "" || name === existing) return;
     try {
       preserveSelectedIdRef.current = taskId;
       const resp = await secureFetch(`${config.apiBaseUrl}/api/task/${taskId}/rename`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         credentials: 'include',
         body: JSON.stringify({ name }),
       });
       if (!resp.ok) {
         const txt = await resp.text().catch(() => "");
         console.error("Rename failed:", txt);
         return;
       }
       setLocalRefreshTick((v) => v + 1);
     } catch (e) {
       console.error("Rename error:", e);
     }
   }, [nodes, secureFetch]);

  const deleteTask = useCallback(async (taskId: string) => {
    const confirmed = window.confirm("Delete this task? This removes its edges but keeps linked entities.");
    if (!confirmed) return;
    try {
      const resp = await secureFetch(`${config.apiBaseUrl}/api/task/${taskId}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      });
      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        console.error("Delete failed:", txt);
        return;
      }
      setSelectedElement((sel) => {
        if (sel && 'id' in sel && sel.id.toString() === taskId) {
          if (onTaskSelected) onTaskSelected(null);
          return null;
        }
        return sel;
      });
      setLocalRefreshTick((v) => v + 1);
    } catch (e) {
      console.error("Delete error:", e);
    }
  }, [onTaskSelected, secureFetch]);

  const notifyTaskSelected = React.useCallback((id: number | null) => {
    if (onTaskSelected) onTaskSelected(id);
  }, [onTaskSelected]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => {
    setSelectedElement(node);
    const n = Number(node.id);
    notifyTaskSelected(Number.isFinite(n) ? n : null);
  };
  const onNodeDoubleClick = async (_: React.MouseEvent, node: Node) => {
    await fleshOutTask(node.id.toString());
  };
  const onNodeContextMenu = (evt: React.MouseEvent, node: Node) => {
    evt.preventDefault();
    evt.stopPropagation();
    openMenuAt(evt.clientX, evt.clientY, node.id.toString());
  };
  const onEdgeClick = (_: React.MouseEvent, edge: Edge) => {
    setSelectedElement(edge);
    notifyTaskSelected(null);
  };

  // Ensure the component tracks the prop-driven project selection
  useEffect(() => {
    if (projectId) setSelectedId(projectId);
  }, [projectId]);

  // Memoize edgeTypes so identity stays stable across renders/HMR
  const edgeTypes = useMemo(() => ({ simplebezier: SimpleBezierEdge, step: StepEdge, straight: StraightEdge }), []);

  // Clear details pane on project change
  React.useEffect(() => {
    setSelectedElement(null);
  }, [selectedId, projectId]);

  // Also listen to external changes (sidebar) and sync selection
  React.useEffect(() => {
    const handler = (e: CustomEvent<{ projectId: number | null }>) => {
      const pid = e.detail?.projectId;
      if (pid !== undefined) {
        setSelectedId(pid);
      }
    };
    window.addEventListener("project-changed", handler as EventListener);
    return () => window.removeEventListener("project-changed", handler as EventListener);
  }, []);

  // Handle selection changes from React Flow (syncs details pane and supports clearing)
  const onSelectionChange = useCallback((params: { nodes: Node[]; edges: Edge[] }) => {
     if (params?.nodes?.length) {
       setSelectedElement(params.nodes[0]);
       const n = Number(params.nodes[0].id);
       notifyTaskSelected(Number.isFinite(n) ? n : null);
       return;
     }
     if (params?.edges?.length) {
       setSelectedElement(params.edges[0]);
       notifyTaskSelected(null);
       return;
     }
     setSelectedElement(null);
     notifyTaskSelected(null);
   }, [notifyTaskSelected]);

   // Clicking the background (pane) clears selection and details
   const onPaneClick = useCallback(() => {
     setSelectedElement(null);
     notifyTaskSelected(null);
   }, [notifyTaskSelected]);

   // Clear task selection when project changes
   useEffect(() => {
     notifyTaskSelected(null);
   }, [projectId, notifyTaskSelected]);

   // Close context menu on outside left-click (bubbling) or Escape
   useEffect(() => {
     const onDocClick = (e: MouseEvent) => {
       if (e.button !== 0) return; // left-click only
       setMenu((m) => ({ ...m, visible: false }));
     };
     const onKey = (e: KeyboardEvent) => {
       if (e.key === 'Escape') setMenu((m) => ({ ...m, visible: false }));
     };
     document.addEventListener('click', onDocClick);
     document.addEventListener('keydown', onKey);
     return () => {
      document.removeEventListener('click', onDocClick);
      document.removeEventListener('keydown', onKey);
     };
   }, []);

  return (
    <div className="h-full w-full border rounded-lg flex flex-col">
      <div className="flex items-center justify-between gap-3 p-2 border-b">
        <div className="text-sm font-medium text-foreground">
          Project: <span className="text-muted-foreground">{projectName}</span>
        </div>
      </div>
      <style jsx global>{`
         /* Base task node: bold black curved outline with translucent light gray bg */
         .react-flow__node.task-node {
           background-color: hsl(var(--muted) / 0.35); /* translucent light gray */
           border: 2px solid #000;
           border-radius: 0.75rem; /* curved rectangle */
           color: hsl(var(--foreground));
           font-size: 12px;
           padding: 10px 12px;
           transition: box-shadow 120ms ease, background-color 120ms ease, border-color 120ms ease;
         }
         .react-flow__node.task-node:hover {
           border-color: #000; /* keep bold black on hover */
           background-color: hsl(var(--muted) / 0.5); /* slightly stronger tint */
         }
         /* Selected: light gray bg + bolder dark outline (matches tree) */
         .react-flow__node.task-node.selected {
           background-color: hsl(var(--muted)) !important; /* light gray */
           border-color: #000 !important;                  /* bold dark outline */
           border-width: 3px !important;                   /* thicker when selected */
           box-shadow: 0 0 0 2px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06) !important;
         }
       `}</style>
       <PanelGroup direction="horizontal" className="flex-1 min-h-0">
         <Panel defaultSize={66} minSize={30}>
           <div ref={containerRef} className="relative h-full w-full">
             <ReactFlow
               onInit={(instance) => {
                 rfInstance.current = instance;
               }}
               nodes={nodes}
               edges={edges}
               onNodesChange={onNodesChange}
               onEdgesChange={onEdgesChange}
               onNodeClick={onNodeClick}
               onNodeDoubleClick={onNodeDoubleClick}
               onNodeContextMenu={onNodeContextMenu}
               onEdgeClick={onEdgeClick}
               onSelectionChange={onSelectionChange}
               onPaneClick={onPaneClick}
               edgeTypes={edgeTypes}
               nodeTypes={nodeTypes}
               fitView
               minZoom={0.2}
             >
               <Controls />
               <Background />
             </ReactFlow>

             {menu.visible && menu.nodeId &&
               createPortal(
                 <div
                   ref={menuRef}
                   className="fixed z-[99999] rounded border border-gray-200 bg-white text-sm shadow-xl w-56 py-1 dark:bg-neutral-900 dark:border-neutral-700"
                   style={{ left: menu.x, top: menu.y }}
                   onContextMenu={(e) => e.preventDefault()}
                   onMouseDown={(e) => e.stopPropagation()}
                   onClick={(e) => e.stopPropagation()}
                 >
                   <button
                     className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-neutral-800"
                     onClick={() => {
                       const id = menu.nodeId!;
                       setMenu((m) => ({ ...m, visible: false }));
                       renameTask(id);
                     }}
                   >
                     Rename
                   </button>
                   <button
                     className="w-full text-left px-3 py-2 text-red-600 hover:bg-gray-100 dark:hover:bg-neutral-800"
                     onClick={() => {
                       const id = menu.nodeId!;
                       setMenu((m) => ({ ...m, visible: false }));
                       deleteTask(id);
                     }}
                   >
                     Delete Task
                   </button>
                 </div>,
                 document.body
               )
             }
           </div>
         </Panel>
         <PanelResizeHandle className="w-2 flex items-center justify-center bg-muted transition-colors hover:bg-muted-foreground/20">
           <div className="h-8 w-1 rounded-full bg-border" />
         </PanelResizeHandle>
         <Panel defaultSize={34} minSize={20}>
           <div className="h-full w-full min-h-0 overflow-hidden">
             <DetailsViewer selectedElement={selectedElement} />
           </div>
         </Panel>
       </PanelGroup>
     </div>
   );
 }
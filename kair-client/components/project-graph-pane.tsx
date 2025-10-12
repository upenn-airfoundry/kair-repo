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
  ReactFlowInstance,
  type EdgeMarker,
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
    // Read computed position from Dagre
    const nodeWithPosition = dagreGraph.node(node.id) as { x: number; y: number };
    node.targetPosition = Position.Left;
    node.sourcePosition = Position.Right;
    // Shift Dagre center anchor to top-left
    node.position = {
      x: nodeWithPosition.x - nodeWidth / 2,
      y: nodeWithPosition.y - nodeHeight / 2,
    };
  });

  return { layoutedNodes: nodes, layoutedEdges: edges };
};

export default function ProjectGraphPane({ projectId, projectName, refreshKey, onTaskSelected }: ProjectGraphPaneProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedElement, setSelectedElement] = useState<Node | Edge | null>(null);
  const secureFetch = useSecureFetch();
  const rfInstance = useRef<ReactFlowInstance | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const onNodesChange: OnNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), [setNodes]);
  const onEdgesChange: OnEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), [setEdges]);

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

  // Use selectedId (fallback to prop) to drive graph fetching
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

        const initialNodes: Node[] = tasksData.tasks.map((task: Task) => ({
          id: task.id.toString(),
          position: { x: 0, y: 0 },
          data: { label: task.name, schema: task.schema },
          className: "task-node",
          style: { width: nodeWidth },
        }));

        const initialEdges: Edge[] = depsData.dependencies.map((dep: Dependency) => {
          const baseStyle: CSSProperties = { stroke: '#333', strokeWidth: 1.5 };
          const edgeStyle: CSSProperties = { ...baseStyle };
          let markerStart: EdgeMarker | undefined;

          if (dep.data_flow === 'rethinking the previous task') {
            edgeStyle.strokeDasharray = '5,5';
          }
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
    })();
  }, [selectedId, projectId, refreshKey, secureFetch]);

  // Fit/center after nodes/edges actually update or project changes
  useEffect(() => {
    if (!rfInstance.current) return;
    // wait a tick so ReactFlow has measured nodes
    const id = requestAnimationFrame(() => resetViewport());
    return () => cancelAnimationFrame(id);
  }, [selectedId, projectId, nodes.length, edges.length, resetViewport]);

  const notifyTaskSelected = React.useCallback((id: number | null) => {
    if (onTaskSelected) onTaskSelected(id);
  }, [onTaskSelected]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => {
    setSelectedElement(node);
    const n = Number(node.id);
    notifyTaskSelected(Number.isFinite(n) ? n : null);
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
  const edgeTypes = useMemo(() => ({ simplebezier: SimpleBezierEdge }), []);

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
          <div className="h-full w-full">
            <ReactFlow
              onInit={(instance) => {
                rfInstance.current = instance;
              }}
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
              onSelectionChange={onSelectionChange}
              onPaneClick={onPaneClick}
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
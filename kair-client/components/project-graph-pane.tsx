'use client';

import { useState, useEffect, useCallback } from 'react';
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
} from 'reactflow';
import 'reactflow/dist/style.css';
import { config } from "@/config";
import DetailsViewer from './details-viewer';
import { useSecureFetch } from '@/hooks/useSecureFetch';
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

interface ProjectGraphPaneProps {
  projectId: number;
  projectName: string;
  refreshKey: number;
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


export default function ProjectGraphPane({ projectId, projectName, refreshKey }: ProjectGraphPaneProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedElement, setSelectedElement] = useState<Node | Edge | null>(null);
  const secureFetch = useSecureFetch();

  const onNodesChange: OnNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), [setNodes]);
  const onEdgesChange: OnEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), [setEdges]);

  useEffect(() => {
    if (!projectId) return;

    const fetchData = async () => {
      try {
        // Fetch tasks and dependencies
        const [tasksRes, depsRes] = await Promise.all([
          secureFetch(`${config.apiBaseUrl}/api/project/${projectId}/tasks`),
          secureFetch(`${config.apiBaseUrl}/api/project/${projectId}/dependencies`)
        ]);
        const tasksData = await tasksRes.json();
        const depsData = await depsRes.json();

        // Create nodes from tasks
        const initialNodes: Node[] = tasksData.tasks.map((task: Task) => ({
          id: task.id.toString(),
          position: { x: 0, y: 0 }, // Position will be set by Dagre
          data: { label: task.name, schema: task.schema },
          style: {
            backgroundColor: '#F0F4FA', // A very light, complementary blue
            border: '1px solid #011F5B', // Penn Blue
            borderRadius: 8,
            padding: '10px 15px',
            fontSize: '12px',
            width: nodeWidth,
            color: '#011F5B', // Use Penn Blue for the text color for better contrast
          },
        }));

        // Create edges from dependencies
        const initialEdges: Edge[] = depsData.dependencies.map((dep: Dependency) => {
          const baseStyle = {
            stroke: '#333', // Darker edge color
            strokeWidth: 1.5, // Slightly thicker edge
          };

          let edgeStyle = { ...baseStyle };
          let markerStart;

          if (dep.data_flow === 'rethinking the previous task') {
            edgeStyle = { ...edgeStyle, strokeDasharray: '5,5' };
          }
          if (dep.data_flow === 'gated by user feedback') {
            markerStart = { type: MarkerType.ArrowClosed, color: '#333', width: 15, height: 15 };
          }

          return {
            id: `e${dep.source}-${dep.target}`,
            source: dep.source.toString(),
            target: dep.target.toString(),
            type: 'bezier', // Use bezier curves for a smoother look
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 20, // Make arrows larger
              height: 20,
              color: '#333',
            },
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
  }, [projectId, refreshKey, secureFetch]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => setSelectedElement(node);
  const onEdgeClick = (_: React.MouseEvent, edge: Edge) => setSelectedElement(edge);

  return (
    <div className="h-full w-full border rounded-lg flex flex-col">
      <h2 className="p-2 font-semibold border-b bg-muted/40">{projectName} - Workflow</h2>
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
              fitView // Re-add fitView
              minZoom={0.2} // Optional: prevent zooming out too far
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
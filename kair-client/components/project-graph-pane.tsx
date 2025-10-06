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
} from 'reactflow';
import 'reactflow/dist/style.css';
import { config } from "@/config";
import DetailsViewer from './details-viewer';

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
  refreshKey: number; // Add the new prop
}

export default function ProjectGraphPane({ projectId, projectName, refreshKey }: ProjectGraphPaneProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedElement, setSelectedElement] = useState<Node | Edge | null>(null);

  const onNodesChange: OnNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), [setNodes]);
  const onEdgesChange: OnEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), [setEdges]);

  useEffect(() => {
    if (!projectId) return;

    const fetchData = async () => {
      try {
        // Fetch tasks and dependencies
        const [tasksRes, depsRes] = await Promise.all([
          fetch(`${config.apiBaseUrl}/api/project/${projectId}/tasks`, { credentials: 'include' }),
          fetch(`${config.apiBaseUrl}/api/project/${projectId}/dependencies`, { credentials: 'include' })
        ]);
        const tasksData = await tasksRes.json();
        const depsData = await depsRes.json();

        // Create nodes from tasks
        const initialNodes: Node[] = tasksData.tasks.map((task: Task, index: number) => ({
          id: task.id.toString(),
          position: { x: (index % 5) * 250, y: Math.floor(index / 5) * 150 },
          data: { label: task.name, schema: task.schema },
          style: {
            backgroundColor: '#F0F4FA', // A very light, complementary blue
            border: '1px solid #011F5B', // Penn Blue
            borderRadius: 8,
            padding: '10px 15px',
            fontSize: '12px',
            width: 180,
            color: '#011F5B', // Use Penn Blue for the text color for better contrast
          },
        }));
        setNodes(initialNodes);

        // Create edges from dependencies
        const initialEdges: Edge[] = depsData.dependencies.map((dep: Dependency) => {
          let style = {};
          let markerStart;
          if (dep.data_flow === 'rethinking the previous task') {
            style = { strokeDasharray: '5,5' };
          }
          if (dep.data_flow === 'gated by user feedback') {
            markerStart = { type: MarkerType.ArrowClosed, color: '#222', width: 20, height: 20 };
          }
          return {
            id: `e${dep.source}-${dep.target}`,
            source: dep.source.toString(),
            target: dep.target.toString(),
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed },
            markerStart,
            style,
            data: dep,
          };
        });
        setEdges(initialEdges);

      } catch (error) {
        console.error("Failed to fetch project graph data:", error);
      }
    };

    fetchData();
  }, [projectId, refreshKey]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => setSelectedElement(node);
  const onEdgeClick = (_: React.MouseEvent, edge: Edge) => setSelectedElement(edge);

  return (
    <div className="h-full w-full border rounded-lg flex flex-col">
      <h2 className="p-2 font-semibold border-b bg-muted/40">{projectName} - Workflow</h2>
      <div className="flex-1 flex min-h-0">
        <div className="w-2/3 h-full border-r">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            fitView
          >
            <Controls />
            <Background />
          </ReactFlow>
        </div>
        <div className="w-1/3 flex flex-col">
          <DetailsViewer selectedElement={selectedElement} />
        </div>
      </div>
    </div>
  );
}
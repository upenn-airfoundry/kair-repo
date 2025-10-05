'use client';

import { useState, useEffect } from 'react';
import { config } from "@/config";
import { Node, Edge } from 'reactflow';

interface DetailsViewerProps {
  selectedElement: Node | Edge | null;
}

// Define a specific type for an entity to avoid using 'any'
interface Entity {
  id: number | string;
  name: string;
  type: string;
  rating: number;
}

export default function DetailsViewer({ selectedElement }: DetailsViewerProps) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (selectedElement && 'position' in selectedElement) { // It's a Node
      setIsLoading(true);
      const fetchEntities = async () => {
        try {
          const response = await fetch(`${config.apiBaseUrl}/api/task/${selectedElement.id}/entities`, { credentials: 'include' });
          const data = await response.json();
          setEntities(data.entities || []);
        } catch (error) {
          console.error("Failed to fetch entities:", error);
          setEntities([]);
        } finally {
          setIsLoading(false);
        }
      };
      fetchEntities();
    } else {
      setEntities([]);
    }
  }, [selectedElement]);

  if (!selectedElement) {
    return <div className="p-4 text-sm text-muted-foreground">Click a node or an edge to see details.</div>;
  }

  // Render Edge Details
  if ('source' in selectedElement) { // It's an Edge
    return (
      <div className="p-4 space-y-2 h-full overflow-y-auto">
        <h3 className="font-bold">Dependency Details</h3>
        <div><strong>From Task:</strong> {selectedElement.source}</div>
        <div><strong>To Task:</strong> {selectedElement.target}</div>
        <div><strong>Description:</strong> {selectedElement.data.relationship_description}</div>
        <div><strong>Data Schema:</strong> {selectedElement.data.data_schema}</div>
        <div><strong>Data Flow:</strong> {selectedElement.data.data_flow}</div>
      </div>
    );
  }

  // Render Node Details
  return (
    <div className="p-4 space-y-2 h-full overflow-y-auto">
      <h3 className="font-bold">Task Entities for &quot;{selectedElement.data.label}&quot;</h3>
      {isLoading ? (
        <p>Loading entities...</p>
      ) : entities.length > 0 ? (
        <ul className="list-disc list-inside">
          {entities.map(entity => (
            <li key={entity.id}>
              {entity.name} <span className="text-xs text-muted-foreground">({entity.type}, Rating: {entity.rating})</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>No entities linked to this task.</p>
      )}
    </div>
  );
}
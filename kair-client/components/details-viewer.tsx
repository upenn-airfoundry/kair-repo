'use client';

import { useState, useEffect } from 'react';
import { config } from "@/config";
import { Node, Edge } from 'reactflow';
import { useSecureFetch } from '@/hooks/useSecureFetch';

interface DetailsViewerProps {
  selectedElement: Node | Edge | null;
}

// Define a specific type for an entity to avoid using 'any'
interface Entity {
  id: number | string;
  name: string;
  type: string;
  detail?: string;
  url?: string;
  rating: number;
}

export default function DetailsViewer({ selectedElement }: DetailsViewerProps) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const secureFetch = useSecureFetch();

  useEffect(() => {
    if (selectedElement && 'position' in selectedElement) { // It's a Node
      setIsLoading(true);
      const fetchEntities = async () => {
        try {
          const response = await secureFetch(`${config.apiBaseUrl}/api/task/${selectedElement.id}/entities`);
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
        <h3 className="font-bold">{selectedElement.data.relationship_description}</h3>
        <div><strong>Schema:</strong> {selectedElement.data.data_schema}</div>
        <div><strong>Dataflow sequencing:</strong> {selectedElement.data.data_flow}</div>
      </div>
    );
  }

  // Render Node Details
  return (
    <div className="p-4 space-y-2 h-full overflow-y-auto">
      <h3 className="font-bold">{selectedElement.data.label} {selectedElement.data.schema}</h3>
      {isLoading ? (
        <p>Loading related resources...</p>
      ) : entities.length > 0 ? (
        <ul className="list-disc list-inside">
          {entities.map(entity => (
            <li key={entity.id}>
              <a href={entity.url} target="_blank" className="font-semibold">{entity.name}</a> <span className="text-xs text-muted-foreground">({entity.type}, Rating: {entity.rating})</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>We haven't yet retrieved resources related to this task.</p>
      )}
    </div>
  );
}
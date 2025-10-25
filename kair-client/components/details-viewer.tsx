'use client';

import { useState, useEffect, useMemo } from 'react';
import { config } from "@/config";
import { Node, Edge } from 'reactflow';
import { useSecureFetch } from '@/hooks/useSecureFetch';
import { Inter_Tight } from 'next/font/google'

const interTight = Inter_Tight({ subsets: ['latin'] })

interface DetailsViewerProps {
  selectedElement: Node | Edge | null;
}

// Entity payload with optional JSON containers
interface Entity {
  id: number | string;
  name?: string;
  type: string;
  detail?: string;
  url?: string;
  rating?: number;
  json?: unknown;
  data?: unknown;
  metadata?: unknown;
  [key: string]: unknown;
}

type JsonObj = Record<string, unknown>;
type JsonShape =
  | { kind: "object"; obj: JsonObj }
  | { kind: "array"; arr: JsonObj[] }
  | { kind: "empty" };

// Try to parse a value into a JSON object or array of objects
function parseJsonShape(val: unknown): JsonShape {
  if (val == null) return { kind: "empty" };

  const asArrayOfObjects = (arr: unknown): JsonShape => {
    if (!Array.isArray(arr)) return { kind: "empty" };
    const objs: JsonObj[] = [];
    for (const item of arr) {
      if (item && typeof item === "object" && !Array.isArray(item)) {
        objs.push(item as JsonObj);
      } else {
        return { kind: "empty" }; // non-object items -> ignore to avoid index keys
      }
    }
    return objs.length ? { kind: "array", arr: objs } : { kind: "empty" };
  };

  if (typeof val === "string") {
    const t = val.trim();
    if (t.startsWith("{") || t.startsWith("[")) {
      try {
        const parsed = JSON.parse(t);
        if (parsed && typeof parsed === "object") {
          if (Array.isArray(parsed)) return asArrayOfObjects(parsed);
          return { kind: "object", obj: parsed as JsonObj };
        }
      } catch {
        /* not JSON */
      }
    }
    return { kind: "empty" };
  }

  if (Array.isArray(val)) {
    return asArrayOfObjects(val);
  }

  if (typeof val === "object") {
    return { kind: "object", obj: val as JsonObj };
  }

  return { kind: "empty" };
}

// Locate the JSON-bearing field of an entity and return its shape
function getEntityJsonShape(e: Entity): JsonShape {
  const candidates = [
    "json",
    "data",
    "metadata",
    "payload",
    "properties",
    "attributes",
    "attrs",
    "content",
    "json_data",
    "json_value",
  ];

  for (const key of candidates) {
    const shape = parseJsonShape((e as Record<string, unknown>)[key]);
    if (shape.kind !== "empty") return shape;
  }

  // Fallback: scan all fields for the first plausible JSON-like structure
  const exclude = new Set(["id", "name", "type", "detail", "url", "rating", "created_at", "updated_at"]);
  for (const [k, v] of Object.entries(e)) {
    if (exclude.has(k)) continue;
    const shape = parseJsonShape(v);
    if (shape.kind !== "empty") return shape;
  }

  return { kind: "empty" };
}

// Parse a schema string like "(title:string,rationale:string,resource:url)"
function parseSchema(schema?: string): string[] {
  if (!schema) return [];
  const s = schema.trim().replace(/^\(/, "").replace(/\)$/, "");
  if (!s) return [];
  const names = s
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => p.split(":")[0]?.trim() || p)
    .filter(Boolean);

  const seen = new Set<string>();
  const out: string[] = [];
  for (const k of names) {
    if (!k || /^\d+$/.test(k)) continue;
    if (k.toLowerCase() === "entity") continue;
    if (!seen.has(k)) {
      seen.add(k);
      out.push(k);
    }
  }
  return out;
}

// Build union of keys across entity JSON payloads (object or array-of-objects)
function collectJsonKeys(entities: Entity[]): string[] {
  const keys = new Set<string>();
  for (const e of entities) {
    const shape = getEntityJsonShape(e);
    const addKeys = (obj: JsonObj) => {
      for (const k of Object.keys(obj)) {
        if (!k || /^\d+$/.test(k)) continue; // skip numeric/empty keys
        if (k.toLowerCase() === "entity") continue; // skip Entity key
        keys.add(k);
      }
    };
    if (shape.kind === "object") addKeys(shape.obj);
    else if (shape.kind === "array") for (const o of shape.arr) addKeys(o);
  }
  return Array.from(keys).sort();
}

function renderValue(val: unknown): string {
  if (val == null) return "";
  if (typeof val === "string") return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  try {
    return JSON.stringify(val);
  } catch {
    return String(val);
  }
}

export default function DetailsViewer({ selectedElement }: DetailsViewerProps) {
  const secureFetch = useSecureFetch();
  const [entities, setEntities] = useState<Entity[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (selectedElement && "position" in selectedElement) {
      setIsLoading(true);
      const fetchEntities = async () => {
        try {
          const response = await secureFetch(`${config.apiBaseUrl}/api/task/${selectedElement.id}/entities`);
          const data = await response.json();
          setEntities(Array.isArray(data?.entities) ? (data.entities as Entity[]) : []);
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
  }, [selectedElement, secureFetch]);

  const isEdge = !!selectedElement && "source" in selectedElement;

  // Extract schema columns from the task node (schema or entity_schema)
  const schemaString = useMemo<string | undefined>(() => {
    if (!selectedElement || !("position" in selectedElement)) return undefined;
    const d = (selectedElement as Node).data as Record<string, unknown> | undefined;
    const s1 = (d?.schema as string | undefined) || (d?.entity_schema as string | undefined);
    return typeof s1 === "string" ? s1 : undefined;
  }, [selectedElement]);

  const schemaCols = useMemo<string[]>(
    () => parseSchema(schemaString),
    [schemaString]
  );

  // Columns from entity JSON keys
  const jsonCols = useMemo<string[]>(
    () => collectJsonKeys(entities),
    [entities]
  );

  // Final columns: schema first, then extra JSON keys not in schema
  const columns = useMemo<string[]>(() => {
    const set = new Set(schemaCols);
    const extras = jsonCols.filter((k) => !set.has(k));
    return [...schemaCols, ...extras];
  }, [schemaCols, jsonCols]);

  // Only keep columns that appear in at least one row (object or any element of an array payload)
  const visibleColumns = useMemo<string[]>(() => {
    if (!columns.length || !entities.length) return columns;
    const present = new Set<string>();
    const checkObj = (obj: JsonObj) => {
      for (const col of columns) {
        if (Object.prototype.hasOwnProperty.call(obj, col)) {
          present.add(col);
        }
      }
    };
    for (const e of entities) {
      const shape = getEntityJsonShape(e);
      if (shape.kind === "object") {
        checkObj(shape.obj);
      } else if (shape.kind === "array") {
        for (const o of shape.arr) checkObj(o);
      }
    }
    return columns.filter((c) => present.has(c));
  }, [columns, entities]);

  if (!selectedElement) {
    return <div className="p-4 text-sm text-muted-foreground">Click a node or an edge to see details.</div>;
  }

  if (isEdge) {
    return (
      <div className={`h-full min-h-0 overflow-auto p-3 space-y-2 text-xs leading-tight ${interTight.className}`}>
        <h3 className="font-bold">{selectedElement.data.relationship_description}</h3>
        <div><strong>Schema:</strong> {selectedElement.data.data_schema}</div>
        <div><strong>Dataflow sequencing:</strong> {selectedElement.data.data_flow}</div>
      </div>
    );
  }

  return (
    <div className={`h-full min-h-0 overflow-hidden flex flex-col text-xs leading-tight ${interTight.className}`}>
      <div className="p-2 pb-1">
        <h3 className="font-semibold tracking-tight text-sm">
          {selectedElement.data.label}
          {schemaString ? (
            <span className="ml-2 text-[10px] text-muted-foreground">{schemaString}</span>
          ) : null}
        </h3>
      </div>

      {isLoading ? (
        <div className="px-2 pb-2 text-[11px] text-muted-foreground">Loading related resources...</div>
      ) : entities.length > 0 ? (
        <div className="flex-1 min-h-0 overflow-auto mx-2 mb-2 rounded-md border">
          <table className="w-full min-w-full text-[11px] table-fixed">
            <thead className="sticky top-0 bg-muted/40 z-10">
              <tr>
                {visibleColumns.map((col) => (
                  <th key={col} className="px-2 py-1 text-left font-semibold tracking-tight text-foreground whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entities.map((e) => {
                const shape = getEntityJsonShape(e);
                if (shape.kind === "object") {
                  const rowObj = shape.obj;
                  return (
                    <tr key={String(e.id)} className="odd:bg-background even:bg-muted/10">
                      {visibleColumns.map((col) => {
                         const raw = rowObj[col];
                         const text = renderValue(raw);
                         const looksLikeUrl = typeof raw === "string" && /^https?:\/\//i.test(raw);
                         return (
                           <td key={col} className="px-2 py-1 align-top break-words whitespace-pre-wrap">
                             {looksLikeUrl ? (
                               <a href={String(raw)} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                                 {text}
                               </a>
                             ) : (
                               <span className="text-foreground/90">{text}</span>
                             )}
                           </td>
                         );
                       })}
                    </tr>
                  );
                } else if (shape.kind === "array") {
                  // Render a row per element, using entity ID as the row key
                  return (
                    <>
                      {shape.arr.map((rowObj) => (
                        <tr key={String(e.id)} className="odd:bg-background even:bg-muted/10">
                          {visibleColumns.map((col) => {
                             const raw = rowObj[col];
                             const text = renderValue(raw);
                             const looksLikeUrl = typeof raw === "string" && /^https?:\/\//i.test(raw);
                             return (
                               <td key={col} className="px-2 py-1 align-top break-words whitespace-pre-wrap">
                                 {looksLikeUrl ? (
                                   <a href={String(raw)} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                                     {text}
                                   </a>
                                 ) : (
                                   <span className="text-foreground/90">{text}</span>
                                 )}
                               </td>
                             );
                           })}
                        </tr>
                      ))}
                    </>
                  );
                }
                // Empty payload -> blank row across columns
                return (
                  <tr key={String(e.id)} className="odd:bg-background even:bg-muted/10">
                    {visibleColumns.map((col) => (
                      <td key={col} className="px-2 py-1 align-top break-words whitespace-pre-wrap"></td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="px-2 pb-2 text-[11px] text-muted-foreground">
           We haven&#39;t yet retrieved resources related to this task.
         </div>
       )}
     </div>
   );
}
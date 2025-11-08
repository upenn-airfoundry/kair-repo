from backend.graph_db import GraphAccessor
from typing import Optional, Any, List, Dict
import logging
import json
import numpy as np
from enrichment.llms import gemini_query_embedding
from prompts.llm_prompts import DecisionPrompts, RequiresHumanDecision

class TaskHelper:
    @classmethod
    def get_gemini_similarity(cls, embed1: List[float], embed2: List[float]) -> float:
        """
        Safe cosine similarity:
        - Handles different vector lengths by truncating to min length.
        - Replaces non-finite values with 0.
        - Returns 0.0 if either vector has zero norm.
        - Returns -1.0 only on unexpected errors.
        """
        try:
            v1 = np.asarray(embed1, dtype=np.float64).ravel()
            v2 = np.asarray(embed2, dtype=np.float64).ravel()
            n = min(v1.size, v2.size)
            if n == 0:
                return -1.0
            if v1.size != v2.size:
                v1 = v1[:n]
                v2 = v2[:n]
            # Replace NaN/Inf with 0 to avoid warnings
            v1[~np.isfinite(v1)] = 0.0
            v2[~np.isfinite(v2)] = 0.0
            n1 = float(np.linalg.norm(v1))
            n2 = float(np.linalg.norm(v2))
            if n1 == 0.0 or n2 == 0.0:
                return 0.0
            return float(np.dot(v1, v2) / (n1 * n2))
        except Exception:
            return -1.0
    
        
    
    @classmethod
    def add_task_entities(cls, graph_accessor: GraphAccessor, task_id: int, entity_contents: dict[str, Any]) -> None:
        """Link entities to a task.

        Args:
            task_id (int): The ID of the task to link entities to.
            entity_ids (List[int]): A list of entity IDs to link to the task.
            entity_contents (dict): A dictionary containing the content of the entities.
        """
        existing_entities = graph_accessor.get_entities_for_task(task_id)
        entities = {}
        # {"id": r[0], "type": r[1], "name": r[2], "detail": r[3], "url": r[4], "rating": r[5]}
        for eid in [row['id'] for row in existing_entities] or []:
            entities[eid] = graph_accessor.get_json(eid)

        for name, e_contents in entity_contents.items():
            entity_id = graph_accessor.add_json(name, '', e_contents)
            if entity_id and entity_id not in entities:
                graph_accessor.link_entity_to_task(task_id, entity_id, 9.0)
                entities[entity_id] = json.dumps(e_contents)

    @classmethod                
    def get_task_entities(cls, graph_accessor: GraphAccessor, task_id: int) -> dict[int, Any]:
        """
        Retrieves all entities associated with a given task, returning a dictionary
        mapping entity IDs to their JSON content.

        Args:
            task_id (int): The ID of the task.

        Returns:
            dict[int, Any]: A dictionary with entity IDs as keys and their JSON objects as values.
        """
        entities = {}
        # get_entities_for_task returns a list of dicts, each with an 'id' key.
        existing_entities = graph_accessor.get_entities_for_task(task_id)
        
        if not existing_entities:
            return entities

        for entity_info in existing_entities:
            
            if entity_id := entity_info.get('id'):
                # get_json retrieves the JSON content for the given entity ID.
                if entity_content := graph_accessor.get_json(entity_id):
                    try:
                        # Ensure the content is a Python object, not a JSON string.
                        entities[entity_id] = json.loads(entity_content) if isinstance(entity_content, str) else entity_content
                    except json.JSONDecodeError:
                        # Handle cases where the content is not valid JSON.
                        logging.warning(f"Could not decode JSON for entity ID {entity_id}")
                        entities[entity_id] = entity_content

        return entities

    @classmethod                
    def modify_task_entities(cls, graph_accessor: GraphAccessor, task_id: int, prompt: str) -> None:
        entities = cls.get_task_entities(graph_accessor, task_id)

        raise NotImplementedError()
        pass
    
    @classmethod                
    def get_most_suitable_task(cls, graph_accessor: GraphAccessor, project_id: int, task_summary: str, selected_task_id: Optional[int]) -> Optional[int]:
        """
        Returns the most suitable task_id for the given task_summary:
          - If selected_task_id belongs to the current project, return it.
          - Otherwise, find an existing task in the project with high embedding similarity to task_summary.
          - If none are suitable, return None.
        """
        # Prefer explicitly selected task if it belongs to this project
        if selected_task_id is not None:
            project = graph_accessor.get_task_project(selected_task_id)
            if project and int(project) == int(project_id):
                return int(selected_task_id)

        # Otherwise, find the most similar existing task in this project
        if not (rows := graph_accessor.get_task_names_for_project(project_id)):
            return None

        # Embed the summary once
        try:
            embed_summary = gemini_query_embedding(task_summary)
        except Exception:
            embed_summary = None

        best_id: Optional[int] = None
        best_sim: float = -1.0
        for task_id, task_name in rows:
            if embed_summary is None:
                continue
            try:
                embed_name = gemini_query_embedding(task_name)
                sim = cls.get_gemini_similarity(embed_name, embed_summary)
                # Original behavior: require a high threshold; keep the best above it
                if sim > 0.9 and sim > best_sim:
                    best_sim = sim
                    best_id = int(task_id)
            except Exception:
                continue
        return best_id
    
    @classmethod
    def get_or_create_task(cls, graph_accessor: GraphAccessor, project_id: int, task_summary: str, selected_task_id: Optional[int], parent_task_id: Optional[int]) -> Optional[int]:
        # Find a suitable existing task or create one
        task_id = cls.get_most_suitable_task(graph_accessor, project_id, task_summary, selected_task_id)
        if task_id is None:
            task_id = graph_accessor.create_project_task(
                project_id,
                task_summary,
                f"Learning resources for project {project_id}",
                "(title:string,rationale:string,url:string)"
            )
            # If this is being created under a parent task, add the parent-subtask edge
            try:
                if parent_task_id is not None:
                    graph_accessor.create_task_dependency(
                        source_task_id=int(parent_task_id),
                        dependent_task_id=int(task_id),
                        relationship_description="Parent to subtask",
                        data_schema="",
                        data_flow="parent task-subtask",
                    )
            except Exception as e:
                logging.warning(f"Failed to create parent->subtask dependency ({parent_task_id} -> {task_id}): {e}")

    @classmethod
    async def requires_human(cls,
                             graph_accessor: GraphAccessor,
                             task: Dict[str, Any],
                             upstream_tasks: List[Dict[str, Any]],
                             downstream_tasks: List[Dict[str, Any]]) -> bool:
        """
        Determine whether 'task' needs human input, given upstream info and downstream needs.
        Returns True if human is required; False if LLM/tools can proceed autonomously.
        """
        task_id = int(task.get("task_id") or task.get("id") or 0)
        task_name = task.get("task_name") or task.get("name") or f"Task {task_id}"
        task_desc = task.get("description") or task.get("task_description") or task.get("goals") or ""
        outputs_schema = task.get("schema") or task.get("outputs_schema") or "(unknown)"

        # Summarize upstream entities/info
        def _safe_join(items: List[str]) -> str:
            return "\n".join(f"- {s}" for s in items if s)

        upstream_entity_summaries: List[str] = []

        # Try to load entity ids linked to upstream tasks
        try:
            upstream_ids = [int(t.get("task_id") or t.get("id")) for t in upstream_tasks if (t.get("task_id") or t.get("id"))]
            entity_ids: List[int] = []
            if upstream_ids:
                entity_ids = graph_accessor.get_entities_for_tasks(upstream_ids)  # List[int]

            if entity_ids:
                ents = graph_accessor.get_entities_with_summaries(entity_ids)  # expect list of dicts
                for e in ents or []:
                    title = e.get("title") or e.get("name") or f"Entity {e.get('id','?')}"
                    summary = e.get("summary") or e.get("abstract") or ""
                    upstream_entity_summaries.append(f"{title}: {summary[:500]}")
        except Exception as e:
            logging.warning(f"Upstream entity summary failed: {e}")

        upstream_text = _safe_join(upstream_entity_summaries)

        # Summarize downstream needs (from dependent tasks' schemas and relationship descriptions)
        downstream_bits: List[str] = []
        for dt in downstream_tasks or []:
            dname = dt.get("task_name") or dt.get("name") or "Dependent Task"
            dneed = dt.get("schema") or dt.get("outputs_schema") or ""
            rel = dt.get("relationship_description") or ""
            if dneed:
                downstream_bits.append(f"{dname} expects: {dneed}")
            if rel:
                downstream_bits.append(f"Criteria/relationship: {rel}")
        downstream_text = _safe_join(downstream_bits)

        decision: RequiresHumanDecision = await DecisionPrompts.requires_human(
            task_name=task_name,
            task_description=task_desc,
            outputs_schema=outputs_schema,
            upstream_text=upstream_text,
            downstream_needs_text=downstream_text
        )
        return bool(decision.requires_human)

    # Optional helper: fetch by IDs from DB
    @classmethod
    async def requires_human_by_id(cls, task_id: int, graph_accessor: GraphAccessor) -> bool:
        """
        Convenience: load the task, its upstream and downstream neighbors from the DB, then decide.
        """
        # Load task core
        row = graph_accessor.get_task_core(task_id)
        if not row:
            return True  # conservative default
        task = {
            "task_id": row["task_id"],
            "task_name": row["task_name"],
            "description": row["task_description"],
            "schema": row["task_schema"],
        }

        # Load dependencies (both directions) and classify upstream/downstream
        deps = graph_accessor.get_dependencies_rows_for_task(task_id) or []

        upstream_tasks: List[Dict[str, Any]] = []
        downstream_tasks: List[Dict[str, Any]] = []
        if deps:
            upstream_ids = [int(r[0]) for r in deps if int(r[1]) == task_id]
            downstream_ids = [int(r[1]) for r in deps if int(r[0]) == task_id]

            # Batch fetch task cores
            upstream_tasks = [
                {
                    "task_id": t["task_id"],
                    "task_name": t["task_name"],
                    "description": t["task_description"],
                    "schema": t["task_schema"],
                }
                for t in graph_accessor.get_tasks_core_by_ids(upstream_ids)
            ]
            downstream_tasks = [
                {
                    "task_id": t["task_id"],
                    "task_name": t["task_name"],
                    "description": t["task_description"],
                    "schema": t["task_schema"],
                }
                for t in graph_accessor.get_tasks_core_by_ids(downstream_ids)
            ]

            # Attach relationship info for downstream
            rel_map: Dict[int, Dict[str, Optional[str]]] = {
                int(r[1]): {"relationship_description": r[2], "data_schema": r[3]}
                for r in deps
                if int(r[0]) == task_id
            }
            for dt in downstream_tasks:
                if info := rel_map.get(int(dt["task_id"])):
                    dt.update(info)

        return await cls.requires_human(graph_accessor, task, upstream_tasks, downstream_tasks)


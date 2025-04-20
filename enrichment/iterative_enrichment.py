##################
## Enrichment
##
## Copyright (C) Zachary G. Ives, 2025
##################


from enrichment.langchain_ops import AssessmentOps
import json

from typing import List

from graph_db import GraphAccessor

DEFAULT_BATCH = 10

def add_strategy(graph_accessor, strategy):
    return

def get_current_best_strategy(graph_accessor, task_description):
    return

def enrich_entities(graph_accessor: GraphAccessor, task: str, entity_set: List[int] = None) -> List[str]:
    criterion = graph_accessor.get_assessment_criteria(task)
    
    ret = []
    
    if criterion is None:
        print(f"Criterion {task} not found.")
        return
    name = criterion['name']
    scope = criterion['scope']
    prompt = criterion['prompt']
    # promise = criterion['promise']
    
    scoped_entities = entity_set;
    if not scoped_entities:
        # Get the relevant scope
        scoped_entities = graph_accessor.get_untagged_papers_by_field(scope, name, DEFAULT_BATCH)

    op = AssessmentOps(prompt, name, 1000)
    
    for paper in scoped_entities:
        result = graph_accessor.get_untagged_entities_as_json(paper['entity_id'], name)
        if result is None:
            continue
        
        jsons = [json.loads(row['json']) for row in result]
        for data in jsons:
            result = op.enrich_data([data])                

            if len(result) == 0:
                print(f"Criterion {name} is empty for paper {paper['entity_id']}")
                graph_accessor.add_tag_to_entity(paper['entity_id'], name, None)
                continue
            
            ret += result[name]
            graph_accessor.add_tag_to_entity(paper['entity_id'], name, result[name])
                
    return result                

def entity_enrichment(graph_accessor: GraphAccessor, entity_set: List[int] = []):
    criteria = graph_accessor.get_assessment_criteria(None)
    
    for criterion in criteria:
        enrich_entities(graph_accessor, criterion['name'], entity_set)
                
def pairwise_enrichment(graph_accessor: GraphAccessor):
    """
    Enrich the database with assessment criteria.
    Find pairs of entities with relevant assessment criteria for relationships.
    """
    return entity_enrichment(graph_accessor)

def iterative_enrichment(graph_accessor: GraphAccessor, task: str = None):
    """
    Enqueue the enrichment tasks.
    """
    # return entity_enrichment(graph_accessor)
    criteria = graph_accessor.get_assessment_criteria(task)
    
    for criterion in criteria:
        graph_accessor.add_task_to_queue(criterion['name'], criterion['scope'])

def process_next_task(graph_accessor: GraphAccessor):
    """
    Fetch the next task from the task_queue and process it using enrichment_task.
    """
    try:
        # Fetch the next task from the queue
        if next_task := graph_accessor.fetch_next_task():
            task_name = next_task["name"]
            task_scope = next_task["scope"]

            print(f"Processing task: {task_name} (Scope: {task_scope})")

            # Call enrichment_task with the task name
            enrich_entities(graph_accessor, task, entities)

            # Delete the task after processing
            graph_accessor.delete_task(next_task["task_id"])
            print(f"Task {task_name} completed and removed from the queue.")
        else:
            print("No tasks in the queue.")
    except Exception as e:
        print(f"Error processing task: {e}")
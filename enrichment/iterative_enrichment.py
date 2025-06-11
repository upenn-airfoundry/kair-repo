##################
## Enrichment
##
## Copyright (C) Zachary G. Ives, 2025
##################


from enrichment.langchain_ops import AssessmentOps
import json

from typing import List

from graph_db import GraphAccessor
import requests

DEFAULT_BATCH = 10

crawled = set()

from crawl.web_fetch import searchapi_for_author, searchapi_for_authorid

search_strategies = {
    "search:google_scholar_author": lambda author_name, searchapi_key: searchapi_for_author(author_name, searchapi_key),
    "search:google_scholar_authorid": lambda author_id, searchapi_key: searchapi_for_authorid(author_id, searchapi_key),
}


def add_strategy(graph_accessor, strategy):
    return

def get_current_best_strategy(graph_accessor, task_description):
    return

def enrich_entities(graph_accessor: GraphAccessor, task: str, entity_set: List[int] = None) -> List[str]:
    criteria = graph_accessor.get_assessment_criteria(task)
    
    ret = []
    
    if criteria is None:
        print(f"Criterion {task} not found.")
        return
    
    for criterion in criteria:
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
                    graph_accessor.add_or_update_tag(paper['entity_id'], name, None)
                    continue
                
                ret += result[name]
                graph_accessor.add_or_update_tag(paper['entity_id'], name, result[name])
                
    return ret                

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
    Enqueue the most promising enrichment tasks for the next round.
    """
    # return entity_enrichment(graph_accessor)
    criteria = graph_accessor.get_assessment_criteria(task)
    
    for criterion in criteria:
        # name: str, scope: str, prompt: str, description: str
        graph_accessor.add_task_to_queue(criterion['name'], criterion['scope'], criterion['prompt'], criterion['name'])
        

def search_entities(graph_accessor: GraphAccessor, task_name: str, task_prompt: str, task_scope: str, task_description: str, searchapi_key: str):
    """
    Search for entities based on the task name and scope.

    Args:
        task_name (str): The name of the task (e.g., "search:google_scholar_author").
        task_scope (str): The scope of the task (e.g., the name of the author).
        searchapi_key (str): The API key for SearchAPI.

    Returns:
        None
    """
    global search_strategies
    if not task_name in search_strategies:
        print(f"Unsupported task name: {task_name}")
        return
    global crawled
    
    if task_scope in crawled:
        print(f"Already crawled for author: {task_scope}")
        return
    crawled.add(task_scope)

    author_name = task_scope
    print(f"Searching for Google Scholar profiles for author: {author_name}")

    # Step 1: Call searchapi_for_author
    profiles = search_strategies[task_name](author_name, searchapi_key)
    if not profiles:
        print(f"No profiles found for author: {author_name}")
        return

    # Step 2: Iterate through the returned list of profiles
    for profile in profiles:
        author_id = profile.get("author_id")
        name = profile.get("name")

        if not author_id or not name or graph_accessor.exists_person(name, author_id, "google_scholar_profile"):
            print(f"Invalid profile data: {profile}")
            continue

        print(f"Processing profile for author: {name} (ID: {author_id})")

        # Step 3: Call searchapi_for_authorid for each (author_id, name) pair
        author_data = search_strategies['search:google_scholar_authorid'](author_id, searchapi_key)
        if not author_data:
            print(f"No detailed data found for author: {name} (ID: {author_id})")
            continue

        # Step 4: Call graph_db.add_person with the Google Scholar URL, name, and author JSON
        google_scholar_url = f"https://scholar.google.com/citations?user={author_id}"
        try:
            graph_accessor.add_person(
                url=google_scholar_url,
                source_type="google_scholar_profile",
                name=name,
                affiliation=author_data['author'].get("affiliations", ""),
                author_json=json.dumps(author_data),
                disambiguator=author_id
            )
            print(f"Added author {name} (ID: {author_id}) to the database.")
        except Exception as e:
            print(f"Error adding author {name} (ID: {author_id}) to the database: {e}")

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
            enrich_entities(graph_accessor, task_name)

            # Delete the task after processing
            graph_accessor.delete_task(next_task["task_id"])
            print(f"Task {task_name} completed and removed from the queue.")
        else:
            print("No tasks in the queue.")
    except Exception as e:
        print(f"Error processing task: {e}")
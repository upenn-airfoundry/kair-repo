##################
## Enrichment
##
## Copyright (C) Zachary G. Ives, 2025
##################


from enrichment.langchain_ops import AssessmentOps
import json

from graph_db import GraphAccessor

# TODO: priority queue of criteria and items

def iterative_enrichment(graph_accessor: GraphAccessor):
    """
    Iteratively enrich the database with assessment criteria.
    For 10 papers that haven't been assessed, apply all assessment criteria.
    """
    criteria = graph_accessor.get_assessment_criteria(None)
    
    for criterion in criteria:
        name = criterion['name']
        scope = criterion['scope']
        prompt = criterion['prompt']
        # promise = criterion['promise']
        
        # Get the relevant scope
        scoped_entities = graph_accessor.get_untagged_papers_by_field(scope, name, 10)
        
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
                
                print (result)
                graph_accessor.add_tag_to_entity(paper['entity_id'], name, result[name])

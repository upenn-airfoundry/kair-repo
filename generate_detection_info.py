##################
## Entity detection, interpretation, and annotation module
##
## Copyright (C) Zachary G. Ives, 2025
##################

import requests
from graph_db import GraphAccessor

# Initialize the GraphAccessor
graph_db = GraphAccessor()

from bs4 import BeautifulSoup
from urllib.parse import unquote
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser

def get_entities_from_db(paper_id: int):

    query = """
SELECT entity_id, paper, array_agg('{ "name": "' || coalesce(author,'') || '", "email": "' || coalesce(email,'') || '", "detail": "' || coalesce(source,'') || '" }') AS authors
                FROM (
                SELECT p.entity_id, '"title": "' || p.entity_name || '", "abstract": "' || summary.tag_value || '", "field": "' || fields.tag_value || '"' AS paper, target.entity_name AS author, replace(target.entity_detail,'"','') AS source, target.entity_contact as email
                FROM entities p JOIN entity_tags summary ON p.entity_id = summary.entity_id
                JOIN entity_tags fields ON p.entity_id = fields.entity_id
                  JOIN entity_link ON p.entity_id = entity_link.to_id
                  JOIN entities AS target ON entity_link.from_id = target.entity_id
                WHERE summary.tag_name = 'summary' AND fields.tag_name = 'field'
                AND p.entity_id = %s
                AND p.entity_type = 'paper' AND target.entity_type = 'author'
            ) GROUP BY entity_id, paper;
    """    
    result = graph_db.exec_sql(query, (paper_id,))
    new_results = []
    for row in result:
        (paper_id, paper_desc, nested) = row
        
        n = '['
        for n2 in nested:
            n += n2 + ', '
        n = n[:-2] + ']'
        
        description = '{' + paper_desc.replace('\n', ' ').replace('\r', ' ') + ', "authors": ' + n.replace('\n', ' ').replace('\r', ' ') + '}'
        new_results.append({"id": paper_id, "json": description})
        # print(f"Paper ID: {paper_id}, Description: {description}")
    return new_results
    


# def get_papers_by_field(field: str, k: int = 1):
#     """
#     Take the field, generate its embedding, match it against entity_tags of type 'field',
#     and find the corresponding 'paper' entities. Print the paper IDs.

#     Args:
#         field (str): The field to search for.
#     """
#     try:
#         # Generate the embedding for the given field
#         field_embedding = graph_db.generate_embedding(field)

#         # Query to match the field embedding against entity_tags of type 'field'
#         query = """
#             SELECT p.entity_id, p.entity_name, t.tag_value
#             FROM entities p
#             JOIN entity_tags t ON p.entity_id = t.entity_id
#             WHERE t.tag_name = 'field'
#             ORDER BY (t.tag_embed <-> %s::vector) ASC
#             LIMIT %s;
#         """
#         results = graph_db.exec_sql(query, (str(field_embedding),k))
        
#         return results

#     except Exception as e:
#         print(f"An error occurred: {e}")


if __name__ == "__main__":
    # Example usage
    field = "medicine"
    results = get_papers_by_field(field, 5)
    
    # Iterate over the results and print the paper IDs
    for row in results:
        (paper_id, name, topic) = row
        print(f"Paper ID: {paper_id}, title: {name}, topic: {topic}")
        # get_entities_from_db(paper_id)


# def update_author_affiliation_in_db(author_id, affiliation):
#     """
#     Update the author's affiliation in the database.
#     """
#     query = "UPDATE entities SET entity_detail = %s, entity_embed = %s WHERE entity_id = %s;"
#     graph_db.execute(query, (affiliation, graph_db.generate_embedding(affiliation), author_id))
#     graph_db.commit()

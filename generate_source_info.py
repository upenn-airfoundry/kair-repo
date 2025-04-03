##################
## Iterate through all authors, organizations, and sources
## and generate tags describing their credibility
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

from prompts.restructure import truncate_text_to_token_limit
from prompts.prompt_from_items import summarize_web_page
from crawl.semscholar import fetch_author_from_semantic_scholar
from crawl.duckduckgo import get_author_homepage

def fix_db():
    query = "SELECT entity_id, entity_detail FROM entities WHERE entity_type = 'author' and entity_detail IS NOT NULL and entity_embed IS NULL"
    results = graph_db.exec_sql(query)
    for author_id, author_detail in results:
        print(f"Processing author ID: {author_id}")
        if author_detail:
            # Generate the embedding for the author detail
            embedding = graph_db.generate_embedding(author_detail)
            # Update the database with the new embedding
            update_query = "UPDATE entities SET entity_embed = %s WHERE entity_id = %s;"
            graph_db.execute(update_query, (embedding, author_id))
    graph_db.commit()

def get_authors_from_db(with_no_affiliation=False):
    """
    Query the list of authors from the entities table.
    """
    if with_no_affiliation:
        query = "SELECT entity_id, entity_name FROM entities WHERE entity_type = 'author' and (entity_detail IS NULL OR length(entity_detail) < 10);"
    else:
        query = "SELECT entity_id, entity_name FROM entities WHERE entity_type = 'author';"
    return graph_db.exec_sql(query)

def update_author_affiliation_in_db(author_id, affiliation):
    """
    Update the author's affiliation in the database.
    """
    query = "UPDATE entities SET entity_detail = %s, entity_embed = %s WHERE entity_id = %s;"
    graph_db.execute(query, (affiliation, graph_db.generate_embedding(affiliation), author_id))
    graph_db.commit()

def process_authors():
    """
    Process all authors in the database, fetch their affiliation from Semantic Scholar,
    and update the database.
    """
    authors = get_authors_from_db(True)
    for author_id, author_name in authors:
        print(f"Processing author: {author_name} (ID: {author_id})")
        author_data = fetch_author_from_semantic_scholar(author_name)
        if author_data and "affiliations" in author_data and author_data["affiliations"]:
            affiliation = author_data["affiliations"][0]["name"]  # Get the first affiliation
            print(f"Found affiliation for {author_name}: {affiliation}")
            update_author_affiliation_in_db(author_id, affiliation)
        else:
            print(f"No affiliation found for {author_name}")
            
            try:
                homepage = get_author_homepage(author_name)
                
                if homepage:
                    # Summarize the web page content using LangChain
                    summary = summarize_web_page(truncate_text_to_token_limit(homepage))
                    print(f"Summary for {author_name}: {summary}")
                    
                    if not "provided HTML" in summary and \
                    "could not be generated" not in summary:
                        # Optionally, update the database with the summary
                        update_author_affiliation_in_db(author_id, summary)
                    
                    # break

            except requests.exceptions.RequestException as e:
                print(f"Error during request: {e}")
            except Exception as e:
                print(f"An error occurred: {e}")
    
if __name__ == "__main__":
    fix_db()
    process_authors()


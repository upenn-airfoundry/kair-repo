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


SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/v1/author/"

from bs4 import BeautifulSoup
from urllib.parse import unquote
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser

import tiktoken

def truncate_text_to_token_limit(text, token_limit=128000):
    """
    Truncates a text string to a specified token limit using tiktoken.

    Args:
        text (str): The text string to truncate.
        token_limit (int): The maximum number of tokens allowed.

    Returns:
        str: The truncated text string.
    """

    encoding = tiktoken.get_encoding("cl100k_base")  # or another appropriate encoding
    tokens = encoding.encode(text)

    if len(tokens) <= token_limit:
        return text  # No truncation needed

    truncated_tokens = tokens[:token_limit]
    truncated_text = encoding.decode(truncated_tokens)
    return truncated_text


def summarize_web_page(content: str) -> str:
    """
    Use LangChain to summarize the content of a web page.
    """
    try:
        # Initialize the LLM (e.g., OpenAI GPT)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that summarizes author biographical information from HTML content."),
            ("user", "Summarize the author info from the following HTML:\n\n{html}"),
        ])

        chain = prompt | llm | StrOutputParser()

        summary = chain.invoke({"html": content})
        return summary
    except Exception as e:
        print(f"Error summarizing web page content: {e}")
        return "Summary could not be generated."

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

def fetch_author_from_semantic_scholar(author_name):
    """
    Look up an author using the Semantic Scholar API and return the top result.
    """
    try:
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/author/search",
            params={"query": author_name, "fields": "name,affiliations"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # print ("name: ", author_name)
        # print ("data: ", data)
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]  # Return the top author
        return None
    except requests.RequestException as e:
        print(f"Error fetching author '{author_name}' from Semantic Scholar: {e}")
        return None

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
                url = f"https://duckduckgo.com/html/?q={author_name}"
                headers = {'User-Agent': 'Mozilla/5.0'} #add headers to avoid blockings.
                response = requests.get(url, headers=headers)
                response.raise_for_status()  # Raise an exception for bad status codes
                
                # print(response.text)
                
                soup = BeautifulSoup(response.text, "html.parser")
                
                search_results = soup.find_all('a', class_='result__url')
                # print(search_results)
                if len(search_results) > 0:
                    first_result = search_results[0]
                    # print(first_result)
                    url = first_result.get('href')
                    
                    url = url.split('?')[1]
                    url = unquote(url.split('&')[0])
                    url = url.split('=')[1]
                    
                    if url.startswith('https://www.researchgate.net'):
                        continue
                    if url.startswith('https://www.linkedin.com'):
                        continue
                    if url.startswith('https://profiles.mountsinai.org'):
                        continue
                    if url.startswith('https://health.usnews.com'):
                        continue
                    if url.startswith('https://iuhealth.org'):
                        continue
                    
                    print(url)
                    
                    headers = {'User-Agent': 'Mozilla/5.0'} #add headers to avoid blockings.
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()  # Raise an exception for bad status codes
                    
                    # print(response.text)
                    
                    

                    # Summarize the web page content using LangChain
                    summary = summarize_web_page(truncate_text_to_token_limit(response.text))
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


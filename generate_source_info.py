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

def get_authors_from_db():
    """
    Query the list of authors from the entities table.
    """
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
    query = "UPDATE entities SET entity_detail = %s WHERE entity_id = %s;"
    graph_db.execute(query, (affiliation, author_id))
    graph_db.commit()

def process_authors():
    """
    Process all authors in the database, fetch their affiliation from Semantic Scholar,
    and update the database.
    """
    authors = get_authors_from_db()
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
                print(search_results)
                if len(search_results) > 0:
                    first_result = search_results[0]
                    print(first_result)
                    url = first_result.get('href')
                    
                    url = url.split('?')[1]
                    url = unquote(url.split('&')[0])
                    url = url.split('=')[1]
                    
                    # print(url)
                    
                    headers = {'User-Agent': 'Mozilla/5.0'} #add headers to avoid blockings.
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()  # Raise an exception for bad status codes
                    
                    # print(response.text)

                    # Summarize the web page content using LangChain
                    summary = summarize_web_page(response.text)
                    print(f"Summary for {author_name}: {summary}")

                    # Optionally, update the database with the summary
                    update_author_affiliation_in_db(author_id, summary)
                    
                    # break

            except requests.exceptions.RequestException as e:
                print(f"Error during request: {e}")
                return None
            except Exception as e:
                print(f"An error occurred: {e}")
                return None
    
if __name__ == "__main__":
    process_authors()


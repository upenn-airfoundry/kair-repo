##################
## Iterate through all authors, organizations, and sources
## and generate tags describing their credibility
##
## Copyright (C) Zachary G. Ives, 2025
##################

import requests
from graph_db import GraphAccessor
from scholarly import scholarly
import requests
from bs4 import BeautifulSoup
import json


from scholarly import ProxyGenerator

# Initialize the GraphAccessor
graph_db = GraphAccessor()


from bs4 import BeautifulSoup
from urllib.parse import unquote
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
import os

from prompts.restructure import truncate_text_to_token_limit
from prompts.prompt_for_documents import summarize_web_page
from crawl.semscholar import fetch_author_from_semantic_scholar
from crawl.duckduckgo import get_author_homepage

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

scraperapi_key = os.getenv("SCRAPER_API_KEY", "your_scraperapi_key")  # Replace with your ScraperAPI key
searchapi_key = os.getenv("SEARCH_API_KEY", "searchapi_key")  # Replace with your ScraperAPI key

# Set up a ProxyGenerator object to use free proxies
# This needs to be done only once per session
# pg = ProxyGenerator()
# pg.FreeProxies()
# scholarly.use_proxy(pg)


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
                        graph_db.add_person(author_name, 'scholar.google.com', summary)
                    
                    # break

            except requests.exceptions.RequestException as e:
                print(f"Error during request: {e}")
            except Exception as e:
                print(f"An error occurred: {e}")

def searchapi_for_author(author_name, searchapi_key) -> list:
    """
    Search for an author using the SearchAPI and return the top result.
    """
    url = f"https://www.searchapi.io/api/v1/search"
    params = {
        "q": author_name,
        "engine": "google_scholar",
        "api_key": searchapi_key
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        if "profiles" in data and len(data["profiles"]) > 0:
            return data["profiles"]
        # if "data" in data and len(data["data"]) > 0:
        #     return data["data"][0]
        return None
    except requests.exceptions.RequestException as e:   
        print(f"Error fetching author '{author_name}' from SearchAPI: {e}")
        return None
        

def searchapi_for_authorid(author_id, searchapi_key) -> list:
    """
    Search for an author using the SearchAPI and return the top result.
    """
    url = f"https://www.searchapi.io/api/v1/search"
    params = {
        "author_id": author_id,
        "engine": "google_scholar_author",
        "api_key": searchapi_key
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        return data
    except requests.exceptions.RequestException as e:   
        print(f"Error fetching author '{author_name}' from SearchAPI: {e}")
        return None
        

def scrape_google_scholar_author(author_id, scraperapi_key):
    """
    Scrapes and parses data from a Google Scholar author profile using ScraperAPI.

    Args:
        author_id (str): The Google Scholar author ID.
        scraperapi_key (str): Your ScraperAPI key.

    Returns:
        dict: A dictionary containing the parsed author data, or None if an error occurs.
    """
    url = f"https://scholar.google.com/citations?view_op=search_authors&mauthors={author_id}&hl=en&oi=ao"
    params = {"api_key": scraperapi_key, "url": url, "render_js": False}

    try:
        response = requests.get("http://api.scraperapi.com", params=params)
        print(response.content)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None
    
    soup = BeautifulSoup(response.content, "html.parser")
    
    author_data = {}
    
    # Extract author information
    author_data["name"] = soup.find("div", id="gsc_prf_in").text.strip()
    author_data["affiliation"] = soup.find("div", class_="gsc_prf_il").text.strip()
    
    # Extract citations
    citation_table = soup.find("table", id="gsc_rs_st")
    citation_rows = citation_table.find_all("tr")
    author_data["citations"] = {}
    author_data["citations"]["all"] = citation_rows[1].find_all("td")[0].text.strip()
    author_data["citations"]["since_2019"] = citation_rows[1].find_all("td")[1].text.strip()
    author_data["h_index"] = {}
    author_data["h_index"]["all"] = citation_rows[2].find_all("td")[0].text.strip()
    author_data["h_index"]["since_2019"] = citation_rows[2].find_all("td")[1].text.strip()
    author_data["i10_index"] = {}
    author_data["i10_index"]["all"] = citation_rows[3].find_all("td")[0].text.strip()
    author_data["i10_index"]["since_2019"] = citation_rows[3].find_all("td")[1].text.strip()
    
    # Extract publications
    publications = []
    pub_table = soup.find("table", id="gsc_a_t")
    pub_rows = pub_table.find_all("tr", class_="gsc_a_tr")
    
    for row in pub_rows:
        pub_data = {}
        cells = row.find_all("td")
        pub_data["title"] = cells[0].find("a", class_="gsc_a_at").text.strip()
        pub_data["authors"] = cells[0].find("div", class_="gs_gray").text.strip()
        pub_data["journal"] = cells[1].text.strip()
        pub_data["citations"] = cells[2].text.strip()
        pub_data["year"] = cells[3].text.strip()
        publications.append(pub_data)
    
    author_data["publications"] = publications

    return author_data

                        
def get_scholar_profile(authors: list[(int, str)]):
    """
    Process all authors in the database, fetch their affiliation from Google Scholar using scholarly,
    and update the database.
    """
    for (author_id, author_name) in authors:
        print(f"Processing author: {author_name} (ID: {author_id})")
        
        try:
            # Search for the author on Google Scholar
            search_query = scholarly.search_author(author_name)
            author_data = next(search_query, None)  # Get the first result
            
            if author_data:
                # Fill in the author's details
                author = scholarly.fill(author_data)
                affiliation = author.get("affiliation", None)
                
                if affiliation:
                    print(f"Found affiliation for {author_name}: {affiliation}")
                    graph_db.add_person(author_name, 'scholar.google.com', affiliation)
                else:
                    print(f"No affiliation found for {author_name}")
            else:
                print(f"No Google Scholar entry found for {author_name}")
        
        except Exception as e:
            print(f"Error processing author {author_name}: {e}")              
    
# if __name__ == "__main__":
#     # fix_db()
#     # process_authors()
#     authors = get_authors_from_db(True)
#     get_scholar_profile(authors)
if __name__ == "__main__":
    author_id = "Daniela De Luca"  # Replace with the author ID
    
    # author_data = scrape_google_scholar_author(author_id, scraperapi_key)
    author_data = searchapi_for_author(author_id, searchapi_key)

    if author_data:
      print(json.dumps(author_data, indent=2))
    else:
        print("Scraping failed.")

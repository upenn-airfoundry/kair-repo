from graph_db import GraphAccessor
import os
import yaml
import requests
import json
from enrichment.llms import analysis_llm
from prompts.prompt_for_documents import extract_faculty_from_html
from prompts.prompt_for_documents import get_page_info

def get_person_subpage_from_directory(graph_accessor: GraphAccessor, url: str, name: str):
    """
    Fetches a person's subpage from a directory and processes it.
    
    :param graph_accessor: An instance of GraphAccessor to interact with the graph database.
    :param url: The URL of the person's subpage.
    """
    response = requests.get(url)
    content = response.text

    if not graph_accessor.is_page_in_cache(url, content):
        graph_accessor.cache_page(url, content)
        
    # TODO: parse with GPT, summarize
    page_info = get_page_info(content, name)
    
    print(url + " - " + name)
    print(json.dumps(page_info, indent=2, ensure_ascii=False))

def get_person_page_from_directory(graph_accessor: GraphAccessor, url: str, name: str, google_scholar: str = None):
    """
    Fetches a person's page from a directory and processes it.
    
    :param graph_accessor: An instance of GraphAccessor to interact with the graph database.
    :param url: The URL of the person's page.
    :param name: The name of the person.
    :param
        google_scholar: Optional; the Google Scholar profile URL of the person.
    """
    response = requests.get(url)
    content = response.text

    if not graph_accessor.is_page_in_cache(url, content):
        graph_accessor.cache_page(url, content)
        
    page_info = get_page_info(content, name)
    
    print(url + " - " + name)
    print(json.dumps(page_info, indent=2, ensure_ascii=False))
    
    for subpage in page_info.get("outgoing_links", []):
        if subpage['category'] != 'other':
            get_person_subpage_from_directory(graph_accessor, subpage['url'], name)
        
    # TODO: parse with GPT, see if it has links to outgoing pages for research sites, personal pages, Google Scholar, etc.
    
    # Identify projects
    # Identify any links to projects
    # Identify papers and any links to papers

def consult_person_directory_page(graph_accessor: GraphAccessor, url: str) -> list:
    """
    Gets a directory page from a department and finds the relevant people, which are then processed.

    Args:
        graph_accessor (GraphAccessor): Database accessor for graph operations.
        url (str): URL of the directory page to consult.
    """
    response = requests.get(url)
    content = response.text

    if not graph_accessor.is_page_in_cache(url, content):
        graph_accessor.cache_page(url, content)
    
    # TODO: parse with GPT, do structured output to the schema:
    # { "name": "XXX",
    #   "titles_or_positions": "XXX",
    #   "homepage": "XXX",
    #   "email": "XXX",
    #   "phone": "XXX",
    #   "address": "XXX",
    #   "affiliations": "XXX",
    #   "research_interests": "XXX",
    #   "google_scholar": "XXX",}
    faculty_list = extract_faculty_from_html(content)
    
    return faculty_list

def consult_person_seeds(graph_accessor: GraphAccessor):
    """Go through the "seed lists" of people directories.ß

    Args:
        graph_accessor (GraphAccessor): graph DB accessor to use for caching and processing.
    """
    starting_points_dir = os.path.join(os.path.dirname(__file__), '../starting_points')
    yaml_file = os.path.join(starting_points_dir, 'people.yaml')
    with open(yaml_file, 'r') as f:
        seeds = yaml.safe_load(f)
        
        content = str(seeds)
        if not graph_accessor.is_page_in_cache("internal://starting_points/people.yaml", content):
            graph_accessor.cache_page("internal://starting_points/people.yaml", content)
        for url in seeds:
            faculty_list = consult_person_directory_page(graph_accessor, url)
            
            # Get the subpages of each person, if they exist
            for faculty in faculty_list['faculty']:
                if 'homepage' not in faculty:
                    continue
                homepage = faculty.get("homepage")
                name = faculty.get("name")
                google_scholar = faculty.get("google_scholar")
                if homepage:
                    get_person_page_from_directory(graph_accessor, homepage, name, google_scholar)
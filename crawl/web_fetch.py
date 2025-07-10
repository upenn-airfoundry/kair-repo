##########
## Fetch PDFs
##
## Copyright (C) 2025 Varun jana
##########

import requests
import pandas as pd
import json
import hashlib
from urllib.parse import parse_qs, quote_plus, urlparse
import time
import os
from graph_db import GraphAccessor

import logging
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from grobid_client.grobid_client import GrobidClient # Note the module structure

import requests
import json
from prompts.prompt_for_documents import extract_faculty_from_html
from prompts.prompt_for_documents import get_page_info

_ = load_dotenv(find_dotenv())

from crawl.crawler_queue import add_to_crawled
from crawl.crawler_queue import get_urls_to_crawl

search_api_key = os.getenv("SEARCH_API_KEY")
graph_db = GraphAccessor()

grobid_client = None
# Need a signature.
#   graph_accessor, url, target, force, qualifier
search_strategies = {
    "search:google_scholar_author": 
        lambda graph_accessor, author_name, provenance, force: scholar_search_gscholar_profiles(graph_accessor, author_name, provenance, force),
    "search:google_scholar_authorid": 
        lambda graph_accessor, author_id, provenance, force: scholar_search_gscholar_by_id(graph_accessor, author_id, provenance, force),    
    "search:member_directory": 
        lambda graph_accessor, url, provenance, force: consult_person_directory_page(graph_accessor, url, provenance, force),
    "search:member_directorypage": 
        lambda graph_accessor, url, provenance, force: get_person_page_from_directory(graph_accessor, url, provenance, force),
    
    "search:member_subpage": 
        lambda graph_accessor, url, provenance, force: get_person_subpage_from_directory(graph_accessor, url, provenance, force)
    
}


# Directory to save downloaded PDFs
DOWNLOADS_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))
GROBID_SERVER = os.getenv("GROBID_SERVER", "http://localhost:8070")



# make a request and wait for it to redirect
def get_redirected_url(doi_url):
  url = ' https://dx.doi.org/' + doi_url
  response = requests.get(url, allow_redirects=False)
  # print(response.headers['Location'])
  return response.headers['Location']




def hash_url(url):
    hash_object = hashlib.sha256(url.encode())
    return hash_object.hexdigest()



def extract_publisher_name(url):
    """
    Extracts the publisher name from a domain.

    Args:
        url (str): The URL from which to extract the publisher name.

    Returns:
        str: The publisher name.
    """
    # Parse the URL
    parsed_url = urlparse(url)
    # Get the hostname (e.g., www.protocols.io)
    hostname = parsed_url.hostname or parsed_url.path
    # Remove 'www.' if present
    hostname = hostname.replace('www.', '') if hostname.startswith('www.') else hostname
    # Split the hostname and take the first part (domain without TLD)
    publisher_name = hostname.split('.')[0]
    return publisher_name


def get_pdf_protocol(url, filename, retry_delay=12, retries=3):
    headers = {
        "Authorization": "Bearer 5d0b895fc7456a9550d6cd1aa4fd1da520e9a08d7ee560b0acf79c49480ae44f95016aeeaaa17eaaffb6513f8b0a4d9da7020789fa5caa7166b3bd223ad5ce59",
        "User-Agent": "curl/7.79.1"
    }

    attempt = 0
    while attempt < retries:
      response = requests.get(url + '.pdf', headers=headers)
      if response.status_code == 200:
          with open(filename, "wb") as file:
              file.write(response.content)
          print(f"Successfully downloaded: {url}")
          return
      if response.status_code == 429:
          print(f"Rate limit exceeded for: {url}. Retry attempt {attempt}/{retries}")
          attempt += 1
          if attempt == retries:
              print(f"Max retries reached for: {url}")
              return
          print(f"Retrying in {retry_delay} seconds...")
          time.sleep(retry_delay)
      else:
          print(f"Failed to download: {url}. Status code: {response.status_code}")
          print(response.text)
          return


# start_id, end_id = 0, 420

# publication_links_df = pd.DataFrame(columns=['DatasetID', 'Publications'])

# for dataset_id in range(start_id, end_id + 1):
#     try:
#         response = get_dataset_metadata(dataset_id)
#         if len(response['datasets']) > 0 and len(response['datasets'][0]['externalPublications']) > 1:
#             # print(f"Dataset ID {dataset_id}:")
#             # print(response['datasets'][0]['externalPublications'])
#             publications = response['datasets'][0]['externalPublications']
#             refined_pubs = [{'relationshipType': publication['relationshipType'], 'url': get_redirected_url(publication['doi'])} for publication in publications]
#             publication_links_df = pd.concat([publication_links_df, pd.DataFrame({'DatasetID': [dataset_id], 'Publications': [refined_pubs]})], ignore_index=True)
#         else:
#             print(f"Dataset ID {dataset_id}: Failed: {response}")
#     except Exception as e:
#         print(f"Dataset ID {dataset_id}: Error - {e}")
        
        
def get_pdf_bioRxiv(url, filename):
  # make request to url to get redirect:
  response = requests.get(url, allow_redirects=False)
  response = requests.get(response.headers['Location'], allow_redirects=False)
  response = requests.get(response.headers['Location'] + '.full.pdf')
  if response.status_code == 200:
      with open(filename, "wb") as file:
          file.write(response.content)
      print(f"Successfully downloaded: {url}")
      return
  else:
      print(f"Failed to download: {url}. Status code: {response.status_code}")
      print(response.text)
      return

  # url = https://www.biorxiv.org/content/10.1101/2020.09.18.303958v1.full.pdf''
  
def get_pdf_frontiersin(url, filename):
    parts = url.split('/')
    article_id = parts[4] + '/' + parts[5]
    journal_abbr = parts[5].split('.')[0]
    journal_abbr_map = {
        'fnins': 'neuroscience',
        'fphys': 'physiology',
        'fnana': 'neuroanatomy',
        'fcell': 'cell-and-developmental-biology'
    }
    if journal_abbr:
        url = 'https://www.frontiersin.org/journals/' + journal_abbr_map.get(journal_abbr, journal_abbr) + '/articles/' + article_id + '/pdf' # type: ignore
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, "wb") as file:
            file.write(response.content)
        print(f"Successfully downloaded: {url}")
    else:
        print(f"Failed to download: {url}. Status code: {response.status_code}")
        print(response.text)


def get_pdf_nature(url, filename):
    response = requests.get(url + '.pdf')
    if response.status_code == 200:
        with open(filename, "wb") as file:
            file.write(response.content)
        print(f"Successfully downloaded: {url}")
    else:
        print(f"Failed to download: {url}. Status code: {response.status_code}")
        print(response.text)

def get_pdf_protocolexchange(url, filename):
    response = requests.get(url + '_covered.pdf')
    if response.status_code == 200:
        with open(filename, "wb") as file:
            file.write(response.content)
        print(f"Successfully downloaded: {url}")
    else:
        print(f"Failed to download: {url}. Status code: {response.status_code}")
        print(response.text)
        
# 338 relations covered
def get_pdf(row):
    if row['PublisherName'] == 'protocols':
        get_pdf_protocol(row['URL'], 'files/' + row['URLHash'] + '.pdf')
        pass
    elif row['PublisherName'] == 'biorxiv':
        get_pdf_bioRxiv(row['URL'], 'biorxiv_files/' + row['URLHash'] + '.pdf')
        pass
    elif row['PublisherName'] == 'linkinghub':
        # manual
        pass
    elif row['PublisherName'] == 'frontiersin':
        get_pdf_frontiersin(row['URL'], 'frontiersin_files/' + row['URLHash'] + '.pdf')
        pass
    elif row['PublisherName'] == 'iopscience':
        # could add a /pdf but manual for now
        print(row['URL'] + '/pdf' + '\t' + row['URLHash'])
        pass
    elif row['PublisherName'] == 'nature':
        get_pdf_nature(row['URL'], row['URLHash'] + '.pdf')
        pass
    elif row['PublisherName'] == 'protocolexchange':
        get_pdf_protocolexchange(row['URL'], 'protocolexchange_files/' + row['URLHash'] + '.pdf')
        pass
    elif row['PublisherName'] == 'onlinelibrary':
        # could modify URL but manual for now

        pass
    else:
        pass
    
def fetch_and_crawl_frontier(downloads_dir: str = DOWNLOADS_DIR):
    # Ensure the downloads directory exists
    os.makedirs(downloads_dir, exist_ok=True)

    rows = get_urls_to_crawl()

    for row in rows:
        crawl_id = int(row['id'])
        url = row['url']
        try:
            if url.startswith('file://'):
                pdf_base = url.split('/')[-1]  # Extract the filename from the URL
                pdf_filename = url[7:]  # Remove the 'file://' prefix
                # if os.path.exists(DOWNLOADS_DIR + "/chunked_files/" + pdf_base + ".json"):
                #     if add_to_crawled(crawl_id, "chunked_files/" + pdf_base + ".json"):  # Mark this PDF as crawled in the database
                #         print(f"Registered pre-chunked file: {pdf_filename}")
                # else:
                if add_to_crawled(crawl_id, url):  # Mark this PDF as crawled in the database
                    logging.debug(f"Registered pre-crawled file: {pdf_base}")
            else:
                file_base = url.split('/')[-1]
                # Save the file locally
                ext_file = f"{crawl_id}-{file_base}"
                filename = os.path.join(DOWNLOADS_DIR, ext_file)
                
                if os.path.exists(filename):
                    logging.debug(f"File {filename} already exists. Skipping download.")
                    add_to_crawled(crawl_id, 'file://' + filename)
                    continue

                # Fetch the PDF from the URL
                response = requests.get(url, timeout=10)
                response.raise_for_status()  # Raise an error for HTTP errors

                with open(filename, "wb") as pdf_file:
                    pdf_file.write(response.content)
                
                global grobid_client
                if grobid_client is None:   
                    grobid_client = GrobidClient(grobid_server=GROBID_SERVER)
                grobid_client.process(
                    service="processFulltextDocument",
                    input_path=downloads_dir,
                    output=downloads_dir + "/tei_xml",
                    # n=10, # Optional: number of concurrent threads, default is usually number of CPU cores
                    # force=True, # Optional: force reprocessing of existing files
                    # tei_coordinates=True, # Optional: to include coordinates in the TEI XML
                    # segment_sentences=True, # Optional: to segment sentences
                )
                    
                if add_to_crawled(crawl_id, ext_file):  # Mark this PDF as crawled in the database
                    logging.info(f"Successfully crawled and saved: {url} to {ext_file}")

        except requests.RequestException as e:
            logging.error(f"Failed to fetch URL {url}: {e}")
        except Exception as e:
            logging.error(f"Error processing crawl ID {crawl_id}: {e}")

    graph_db.commit()
    
def searchapi_for_authorid(author_id: str, searchapi_key: str) -> dict:
    """
    Search Google Scholar for author profiles using SearchAPI.

    Args:
        author_id (str): The name of the author to search for.
        searchapi_key (str): The API key for SearchAPI.

    Returns:
        author profile info
    """
    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": "google_scholar_author",
        "author_id": author_id,
        "api_key": searchapi_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except Exception as e:
        print(f"Error searching for author '{author_id}': {e}")
        return {}

def searchapi_for_author(author_name: str, searchapi_key: str) -> list[dict]:
    """
    Search Google Scholar for author profiles using SearchAPI.

    Args:
        author_id (str): The name of the author to search for.
        searchapi_key (str): The API key for SearchAPI.

    Returns:
        list: A list of author profile dictionaries, or an empty list if none found.
    """
    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": "google_scholar",
        "q": f'author:{quote_plus(author_name)}',
        "api_key": searchapi_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("profiles", [])
    except Exception as e:
        print(f"Error searching for author '{author_name}': {e}")
        return []

def consult_person_directory_page(graph_accessor: GraphAccessor, url: str, provenance: list[str], force: bool = True) -> list:
    """
    Gets a directory page from a department and finds the relevant people's pages, which are then queued as tasks.
    If a Google Scholar profile is found, it is also queued for further processing.

    Args:
        graph_accessor (GraphAccessor): Database accessor for graph operations.
        url (str): URL of the directory page to consult.
        provenance (list[str]): A list of steps by which we arrived here.
        force (bool): Whether to force a new fetch even if cached data exists.
    """
    response = requests.get(url)
    content = response.text
    
    provenance.append(url)

    faculty_list = []
    force = True
    if force or not graph_accessor.is_page_in_cache(url, content):
        faculty_list = extract_faculty_from_html(content)
        graph_accessor.cache_page_and_results(url, content, json.dumps(faculty_list, ensure_ascii=False))
        
    else:
        faculty_list = graph_accessor.get_cached_output(url, content)
        # If the page is not cached, parse it to extract faculty information
        
    if not faculty_list:
        print(f"No faculty information found on the page: {url}")
        return [{'faculty': []}]
    
    # graph_accessor.add_person_info_page(
    #     url,
    #     name,
    #     "organizational directory page for a person",
    #     content)
        
    # Follow up by requesting searches of the linked personal pages
    for faculty in faculty_list.get('faculty', []):
        name = faculty.get("name")
        homepage = faculty.get("homepage")
        google_scholar = faculty.get("google_scholar")
        
        if not name:
            print(f"Skipping entry without a name: {faculty}")
            continue
        
        provenance.append(name)
        # If the homepage is not provided, we can use the Google Scholar profile
        if not homepage and google_scholar:
            parsed = urlparse(google_scholar)
            query = parsed.query
            qs = parse_qs(query)
            scholar_id = qs.get('user', [None])[0]
            if not scholar_id:
                print(f"Could not extract Google Scholar ID from URL: {google_scholar}")
                continue
            graph_accessor.add_task_to_queue(
                'search:google_scholar_authorid',
                scholar_id,
                f"Fetch the Google Scholar page for {name} from Google Scholar profile.",
                json.dumps(provenance)
            )
        elif homepage:        
            graph_accessor.add_task_to_queue(
                'search:member_directorypage',
                homepage,
                f"Fetch the directory page for {name} from homepage.",
                json.dumps(provenance)
            )
            if google_scholar:
                # If a Google Scholar profile is provided, queue it for processing
                parsed = urlparse(google_scholar)
                query = parsed.query
                qs = parse_qs(query)
                scholar_id = qs.get('user', [None])[0]
                if not scholar_id:
                    print(f"Could not extract Google Scholar ID from URL: {google_scholar}")
                    continue
                graph_accessor.add_task_to_queue(
                    'search:google_scholar_authorid',
                    scholar_id,
                    f"Fetch the Google Scholar profile for {name}.",
                    json.dumps(provenance)
                )
            
        provenance.pop()  # Remove the last element (name) from provenance as it is already used in the task
        
    return faculty_list


# TODO:
# - Integrate items into task queue (start with seed pages)
# - Add dispatcher from task queue for searches, including unmarshalling the provenance
# - Add handler for fetch PDF task
# - Add error handling for network requests
# - Increase crawl rate
# - Update personal page crawl, fetch + cache
# - Update subpage / link crawl, fetch + cache
# - Allow for going out another step to get project pages, papers, etc.

def get_person_page_from_directory(graph_accessor: GraphAccessor, url: str, provenance: list[str], force: bool = True):
    """
    Fetches a person's page from a directory and processes it.  Also looks for links to subpages.
    
    :param graph_accessor: An instance of GraphAccessor to interact with the graph database.
    :param url: The URL of the person's page.
    :param name: The name of the person.
    :param
        google_scholar: Optional; the Google Scholar profile URL of the person.
    """
    response = requests.get(url)
    content = response.text
    
    if url in provenance:
        print(f"Already visited {url}, skipping.")
        return
    
    if len(provenance) < 1:
        name = "Unknown Person"
        return
    else:
        name = provenance[-1]
        
    provenance.append(url)
    if force or not graph_accessor.is_page_in_cache(url, content):
        page_info = get_page_info(content, name)
        graph_accessor.cache_page_and_results(url, content, json.dumps(page_info, ensure_ascii=False))
    else:
        page_info = graph_accessor.get_cached_output(url, content)

    print(url + " - " + name)
    print(json.dumps(page_info, indent=2, ensure_ascii=False))
    
    # get entry on the author (by Google Scholar ID or canonical name)
    # Summarize the current page
    # If there is an existing summary,
    # concatenate the existing entry with the new information on the page 
    # summarize
    # Then update the graph with the new information

    # Unclassified page type when we expected a homepage, skip out    
    if page_info is None or page_info.get("category") == "other":
        return []
    
    # record the page in the graph database
    graph_accessor.add_person_info_page(
        url,
        name,
        page_info.get("category", "other"),
        content
    )
    
    for subpage in page_info.get("outgoing_links", []):
        if subpage['url'] in provenance:
            print(f"Already visited {subpage['url']}, skipping.")
            
        elif subpage['category'] == 'google scholar profile':
            # Extract Google Scholar ID from the URL (e.g., .../citations?user=XXXX)
            parsed = urlparse(subpage['url'])
            query = parsed.query
            qs = parse_qs(query)
            scholar_id = qs.get('user', [None])[0]
            if not scholar_id:
                print(f"Could not extract Google Scholar ID from URL: {subpage['url']}")
                continue
            provenance.append(name)
            graph_accessor.add_task_to_queue(
                'search:google_scholar_authorid',
                scholar_id,
                f"Search for Google Scholar profile for author ID: {subpage['url']}",
                json.dumps(provenance)
            )
            provenance.pop()
        elif subpage['category'] == 'organizational directory page for a person':
        #     provenance.append(name)
        #     graph_accessor.add_task_to_queue(
        #         'search:member_directorypage',
        #         subpage['url'],
        #         f"Fetch the subpage for {name} from directory page.",
        #         json.dumps(provenance)
        #     )
            print(f"Skipping organizational directory page for {name} as it is already processed: {subpage['url']}")
        elif subpage['category'] == subpage['category'] == 'personal or professional homepage':
            provenance.append(name)
            graph_accessor.add_task_to_queue(
                'search:member_subpage',
                subpage['url'],
                f"Fetch the subpage for {name} from directory page.",
                json.dumps(provenance)
            )
            provenance.pop()
        elif subpage['category'] != 'other':
            # get_person_subpage_from_directory(graph_accessor, subpage['url'], name, [url], force)
            provenance.append(name)
            graph_accessor.add_task_to_queue(
                'search:member_subpage',
                subpage['url'],
                f"Fetch the subpage for {name} from directory page.",
                json.dumps(provenance)
            )        
            provenance.pop()


def get_person_subpage_from_directory(graph_accessor: GraphAccessor, url: str, visited: list[str], force: bool = True):
    """
    Fetches a person's subpage from a directory and processes it.  It could be a research or teaching page, etc.
    
    :param graph_accessor: An instance of GraphAccessor to interact with the graph database.
    :param url: The URL of the person's subpage.
    """
    try:
        if not url.startswith('http'):
            # Find the most recent URL in visited (from last to first)
            base_url = None
            for prev in reversed(visited):
                if prev.startswith('http'):
                    base_url = prev
                    break
            if base_url:
                url = requests.compat.urljoin(base_url, url)
            else:
                print(f"Invalid URL: {url}. Skipping.")
                return
            
        if len(graph_accessor.get_entity_ids_by_url(url)):
            print(f"Already processed {url}, skipping.")
            return
            
        response = requests.get(url)
        content = response.text

        name = visited[-1]
        visited.append(url)
        if force or not graph_accessor.is_page_in_cache(url, content):
            page_info = get_page_info(content, name)
            graph_accessor.cache_page_and_results(url, content, json.dumps(page_info, ensure_ascii=False))
        else:        
            page_info = graph_accessor.get_cached_output(url, content)
            # parse with GPT, summarize
            
        if page_info is None:
            page_info = get_page_info(content, name)
            graph_accessor.cache_page_and_results(url, content, json.dumps(page_info, ensure_ascii=False))
            
        print(url + " - " + name)
        print(json.dumps(page_info, indent=2, ensure_ascii=False))
        
        if page_info.get("category") == "other":
            # If the page is categorized as 'other', we might want to skip it or handle it differently
            print(f"Skipping {url} as it is categorized as 'other'.")
            return
        
        # record the page in the graph database
        graph_accessor.add_person_info_page(
            url,
            name,
            page_info.get("category", "other"),
            content
        )
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
    

def scholar_search_gscholar_profiles(graph_accessor: GraphAccessor, author_name: str, provenance: list[str], force: bool = False) -> list:
    """
    Search Google Scholar for author profiles using SearchAPI by author name.
    
    There may be multiple profiles for the same author, so this function retrieves all profiles.  
    It also puts them into the task queue for further processing.
    
    Args:
        author_name (str): The name of the author to search for.
        provenance (list[str]): A list of provenance strings for the search, with the name as the last term.
        force (bool): Whether to force a new search even if cached data exists.
    Returns:
        List of author profiles in Google Scholar
    """
    global search_api_key
    
    url = f'https://scholar.google.com/scholar?q=author:{quote_plus(author_name)}'

    content = None    
    text = requests.get(url).text
    if force or not graph_accessor.is_page_in_cache(url, text):
        content = searchapi_for_author(author_name, search_api_key)
        graph_accessor.cache_page_and_results(url, text, content)
    else:        
        content = graph_accessor.get_cached_output(url, text)

    profiles = content.get("profiles", [])            
    if not profiles:
        print(f"No profiles found for author: {author_name}")
        return []

    # Iterate through the returned list of profiles and queue up a task for each profile
    for profile in profiles:
        author_id = profile.get("author_id", None)
        name = profile.get("name", None)

        if not author_id or not name:
            print(f"Invalid profile data: {profile}")
            continue

        print(f"Enqueuing profile for author: {name} (ID: {author_id})")
        
        graph_accessor.add_task_to_queue(
            'search:google_scholar_authorid',
            author_id,
            f"Search for Google Scholar profile for author ID: {author_id}",
            f"Search for detailed information about the author with ID: {author_id} on Google Scholar."
        )

    return profiles

def scholar_search_gscholar_by_id(graph_accessor: GraphAccessor, author_id: str, provenance: list[str], force: bool = False) -> list:
    """
    Search Google Scholar for author profiles using SearchAPI by author ID.
    
    Indexes each author profile in the graph database.
    
    This function retrieves detailed information about an author using their Google Scholar ID.
    It first checks if the data is cached, and if not, it fetches the data using SearchAPI.    
    It then extracts the author's name from the data or uses the last term in the provenance list as a fallback.
    Finally, it adds the author to the graph database with their Google Scholar profile URL, name, affiliation, and author JSON.
    
    Args:
        author_id (str): The ID of the author to search for.
        provenance (list[str]): A list of provenance strings for the search, with the name as the last term.
        force (bool): Whether to force a new search even if cached data exists.
    Returns:
        list: A list of author profile dictionaries, or an empty list if none found.
    """
    global search_api_key

    url = f'https://scholar.google.com/citations&user={quote_plus(author_id)}'    
    content = None
    text = requests.get(url).text
    if force or not graph_accessor.is_page_in_cache(url, text):
        # Call searchapi_for_authorid for each (author_id, name) pair
        author_data = searchapi_for_authorid(author_id, search_api_key)
        graph_accessor.cache_page_and_results(url, text, json.dumps(author_data))
    else:        
        author_data = graph_accessor.get_cached_output(url, text)
    
    if not author_data:
        print(f"No detailed data found for author: {author_id} from {provenance})")
        return []

    # Extract the name from the Google record or else the last term in provenance
    name = author_data['author'].get("name", provenance[-1])
    
    # Call graph_db.add_person with the Google Scholar URL, name, and author JSON
    google_scholar_url = f"https://scholar.google.com/citations?user={author_id}"
    try:
        graph_accessor.add_person(
            google_scholar_url,
            "google_scholar_profile",
            name,  # Use the last term in provenance as the name
            author_data['author'].get("affiliations", ""),
            json.dumps(author_data),
            author_id
        )
        graph_accessor.add_person_info_page(
            google_scholar_url,
            name,
            "scholar profile " + author_id,
            json.dumps(author_data))
        print(f"Added author {name} (ID: {author_id}) to the database.")
    except Exception as e:
        print(f"Error adding author {name} (ID: {author_id}) to the database: {e}")


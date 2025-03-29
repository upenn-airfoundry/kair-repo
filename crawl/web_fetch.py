##########
## Fetch PDFs
##
## Copyright (C) 2025 Varun jana
##########

import requests
import pandas as pd
import json
import hashlib
from urllib.parse import urlparse
import time

def get_dataset_metadata(dataset_id):
    base_url = "https://api.pennsieve.io/discover/datasets?ids={dataset_id}"
    headers = {
        "accept": "application/json"
    }
    response = requests.get(base_url.format(dataset_id=dataset_id), headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return None

def get_publication_links(dataset_id, relationship_type='IsDescribedBy'):
  try:
    publications = get_dataset_metadata(dataset_id)['datasets'][0]['externalPublications']
    count = 0
    for publication in publications:
        if publication['relationshipType'] == 'IsDescribedBy':
            count += 1
            # print(publication)
            # return publication
    print(count)
    return None
  except Exception as e:
    # print(e)
    return None

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


start_id, end_id = 0, 420

publication_links_df = pd.DataFrame(columns=['DatasetID', 'Publications'])

for dataset_id in range(start_id, end_id + 1):
    try:
        response = get_dataset_metadata(dataset_id)
        if len(response['datasets']) > 0 and len(response['datasets'][0]['externalPublications']) > 1:
            # print(f"Dataset ID {dataset_id}:")
            # print(response['datasets'][0]['externalPublications'])
            publications = response['datasets'][0]['externalPublications']
            refined_pubs = [{'relationshipType': publication['relationshipType'], 'url': get_redirected_url(publication['doi'])} for publication in publications]
            publication_links_df = pd.concat([publication_links_df, pd.DataFrame({'DatasetID': [dataset_id], 'Publications': [refined_pubs]})], ignore_index=True)
        else:
            print(f"Dataset ID {dataset_id}: Failed: {response}")
    except Exception as e:
        print(f"Dataset ID {dataset_id}: Error - {e}")
        
        
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
    url = 'https://www.frontiersin.org/journals/' + journal_abbr_map.get(journal_abbr, journal_abbr) + '/articles/' + article_id + '/pdf'
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
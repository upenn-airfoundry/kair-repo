
import requests

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

    return publications
  except Exception as e:
    print(e)
    return None

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/v1/author/"

import requests

from prompts.restructure import truncate_text_to_token_limit
from prompts.prompt_from_items import summarize_web_page


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


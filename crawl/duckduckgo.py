import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

def get_author_homepage(author_name: str) -> str:
    """
    Fetch the author's homepage from the Semantic Scholar API.
    """
    try:
        url = f"https://duckduckgo.com/html/?q={author_name}"
        headers = {'User-Agent': 'Mozilla/5.0'} #add headers to avoid blockings.
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        
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
                return None
            if url.startswith('https://www.linkedin.com'):
                return None
            if url.startswith('https://profiles.mountsinai.org'):
                return None
            if url.startswith('https://health.usnews.com'):
                return None
            if url.startswith('https://iuhealth.org'):
                return None
            
            print(url)
            
            headers = {'User-Agent': 'Mozilla/5.0'} #add headers to avoid blockings.
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            return response.text

    except requests.exceptions.RequestException as e:
        print(f"Error during request: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

    



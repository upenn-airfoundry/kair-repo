import arxiv
import requests
import os

def search_by_arxiv_id(arxiv_id: str) -> dict:
    """
    Search for a paper by its ArXiv ID.

    Args:
        arxiv_id (str): The ArXiv ID of the paper.

    Returns:
        dict: A dictionary containing the paper's details, or None if not found.
    """
    try:
        search = arxiv.Search(id_list=[arxiv_id])
        for result in search.results():
            return {
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary,
                "published": result.published,
                "pdf_url": result.pdf_url,
            }
        return None
    except Exception as e:
        print(f"Error searching by ArXiv ID: {e}")
        return None

def search_by_author(author_name: str, max_results: int = 10) -> list:
    """
    Search for papers by an author's name.

    Args:
        author_name (str): The name of the author.
        max_results (int): The maximum number of results to return.

    Returns:
        list: A list of dictionaries containing paper details.
    """
    try:
        search = arxiv.Search(
            query=f"au:{author_name}",
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        results = []
        for result in search.results():
            results.append({
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary,
                "published": result.published,
                "pdf_url": result.pdf_url,
            })
        return results
    except Exception as e:
        print(f"Error searching by author: {e}")
        return []

def search_by_query(query: str, max_results: int = 10) -> list:
    """
    Search for papers using a general query.

    Args:
        query (str): The search query.
        max_results (int): The maximum number of results to return.

    Returns:
        list: A list of dictionaries containing paper details.
    """
    try:
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = []
        for result in search.results():
            results.append({
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary,
                "published": result.published,
                "pdf_url": result.pdf_url,
            })
        return results
    except Exception as e:
        print(f"Error searching by query: {e}")
        return []

def download_pdf(pdf_url: str, save_path: str) -> bool:
    """
    Download a PDF from an arXiv URL.

    Args:
        pdf_url (str): The URL of the PDF to download.
        save_path (str): The file path where the PDF should be saved.

    Returns:
        bool: True if the download was successful, False otherwise.
    """
    try:
        response = requests.get(pdf_url, stream=True)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Save the PDF to the specified path
        with open(save_path, "wb") as pdf_file:
            for chunk in response.iter_content(chunk_size=8192):
                pdf_file.write(chunk)

        print(f"PDF downloaded successfully: {save_path}")
        return True
    except Exception as e:
        print(f"Error downloading PDF: {e}")
        return False
    

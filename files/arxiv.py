import json
from graph_db import GraphAccessor

from prompts.prompt_for_documents import classify_json

def load_arxiv_abstracts(jsonl_path="starting_points/arxiv-metadata-oai-snapshot.json"):
    """
    Loads arXiv abstracts from a JSONL file and inserts papers and tags into the database.
    """
    accessor = GraphAccessor()
    with open(jsonl_path, "r") as f:
        i = 0
        for line in f:
            i += 1
            try:
                row = json.loads(line)
                doi = row.get("doi")
                if not doi:
                    continue  # skip if no DOI
                doi = "https://doi.org/" + doi
                url = "https://arxiv.org/pdf/" + row.get("id", "").strip()
                
                title = row.get("title", "").strip()
                abstract = row.get("abstract", "").strip()
                authors_parsed = row.get("authors_parsed", [])
                
                # Skip any we have already parsed and indexed
                if accessor.is_paper_in_db(url):
                    # print(f"Updating DOI for arXiv paper {i}: {title} ({url})")
                    # paper_id = accessor.get_entity_ids_by_url(url, type='paper')[0]
                    # accessor.add_or_update_tag(paper_id, "doi", doi, add_another=False)
                    continue
                else:
                    print(f"Processing arXiv paper {i}: {title} ({url})")
                    # Insert paper entity (implement add_paper as needed)
                    paper_id = accessor.add_paper(url, title, abstract)
                    accessor.add_or_update_tag(paper_id, "doi", doi, add_another=False)

                # Add summary tag (abstract) -- already done by add_paper
                # accessor.add_or_update_tag(paper_id, "summary", abstract, add_another=False)

                # Add author tags
                for author in authors_parsed:
                    last = author[0]
                    first = ""
                    if len(author) < 2:
                        continue
                    else:
                        first = author[1]
                    #last, first, _ = author
                    full_name = f"{first} {last}".strip()
                    accessor.add_author_tag(paper_id, full_name)
            except Exception as e:
                print(f"Error processing row: {e}")
                
def classify_arxiv_categories(jsonl_path="starting_points/arxiv-metadata-oai-snapshot.json"):
    """
    Loads arXiv abstracts from a JSONL file and inserts papers and tags into the database.
    """
    accessor = GraphAccessor()
    with open(jsonl_path, "r") as f:
        i = 0
        for line in f:
            i += 1
            try:
                row = json.loads(line)
                url = "https://arxiv.org/pdf/" + row.get("id", "").strip()
                paper_ids = accessor.get_entity_ids_by_url(url, type='paper')
                
                if (paper_ids):                
                    the_class = classify_json(row)
                    
                    if the_class:
                        print(f"Classifying arXiv paper {i}: {row.get('title', '')} ({row.get('id', '')}) as {the_class}")
                        accessor.add_or_update_tag(
                            paper_ids[0], 
                            "field", 
                            the_class, 
                            add_another=False
                        )
            except Exception as e:
                print(f"Error processing row: {e}")
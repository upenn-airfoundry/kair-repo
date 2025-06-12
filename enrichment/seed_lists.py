from graph_db import GraphAccessor
import os
import yaml
import json
from prompts.prompt_for_documents import is_about

from crawl.web_fetch import get_person_page_from_directory, consult_person_directory_page

def consult_person_seeds(graph_accessor: GraphAccessor, force: bool = True):
    """Go through the "seed lists" of people directories.

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
            graph_accessor.add_task_to_queue(
                "search:member_directory",
                url,
                "consult_person_directory",
                json.dumps([url])
            )
            # faculty_list = consult_person_directory_page(graph_accessor, url)
            
            # # Get the subpages of each person, if they exist
            # for faculty in faculty_list['faculty']:
            #     homepage = faculty.get("homepage")
            #     name = faculty.get("name")
            #     google_scholar = faculty.get("google_scholar")
            #     if google_scholar and is_about(google_scholar, name):
            #         uuid = google_scholar.split('=')[-1]
            #     else:
            #         # Get homepage tld from url:
            #         uuid = url.split('//')[-1].split('/')[0] + "/" + name.replace(" ", "_").lower()
            #     visited = set()
            #     if homepage:
            #         get_person_page_from_directory(graph_accessor, homepage, name, visited, force, uuid)
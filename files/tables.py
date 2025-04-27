import pandas as pd
import random
from scipy.io import loadmat

from prompts.prompt_for_tables import describe_table
from graph_db import GraphAccessor

SAMPLE_SIZE = 50

def read_csv(file_path: str) -> pd.DataFrame:
    """
    Read a CSV file into a DataFrame.
    """
    return pd.read_csv(file_path)

def read_json(file_path: str) -> pd.DataFrame:
    """
    Read a JSON file into a DataFrame.
    """
    return pd.read_json(file_path)

def read_jsonl(file_path: str) -> pd.DataFrame:
    """
    Read a JSON file into a DataFrame.
    """
    return pd.read_json(file_path,lines=True )

def read_xml(file_path: str) -> pd.DataFrame:
    """
    Read an XML file into a DataFrame.
    """
    return pd.read_xml(file_path)

def read_mat(file_path: str) -> pd.DataFrame:
    """
    Read a Matlab MAT file into a DataFrame.
    """
    mat_data = loadmat(file_path)
    # Assuming the MAT file contains a single table-like structure
    # Convert the first key-value pair to a DataFrame
    for key, value in mat_data.items():
        if isinstance(value, (list, pd.DataFrame)):
            return pd.DataFrame(value)
    raise ValueError("No table-like structure found in the MAT file.")

def sample_rows_to_string(df: pd.DataFrame, rows:int=SAMPLE_SIZE) -> pd.DataFrame:
    """
    Randomly sample SAMPLE_SIZE rows from the DataFrame and return as a string.
    """
    sample_size = min(SAMPLE_SIZE, len(df))
    sampled_df = df.sample(n=sample_size, random_state=42)
    return sampled_df

def create_table_entity(url: str, df: pd.DataFrame, graph_db: GraphAccessor):
    
    # Get a description of the table using the LLM
    description = describe_table(url.split('/')[-1], df)
    
    # Create the table entity in the graph database
    entity_id = graph_db.add_table(url, url.split('/')[-1], description)
    
    # Add the table itself
    table_id = graph_db.index_dataframe(df, entity_id)
    
    # TODO:     # (Should we create a sample annotation per column? A sketch per column?)

    return table_id
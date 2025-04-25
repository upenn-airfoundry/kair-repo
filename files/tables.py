import pandas as pd
import random
from scipy.io import loadmat

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
    return pd.read_json(file_path, )

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

def sample_rows_to_string(df: pd.DataFrame) -> str:
    """
    Randomly sample SAMPLE_SIZE rows from the DataFrame and return as a string.
    """
    sample_size = min(SAMPLE_SIZE, len(df))
    sampled_df = df.sample(n=sample_size, random_state=42)
    return sampled_df.to_string(index=False)

def create_table_entity(df: pd.DataFrame, graph_db: GraphAccessor):
    sample_content = sample_rows_to_string(df)
    
    # TODO: (1) generate schema description alongside sample, (2) create entity, (3) create annotation
    # (Should we create a sample annotation per column? A sketch per column?)
    # Also create a table in the indexed_tables schema, with a well-chosen name
    return
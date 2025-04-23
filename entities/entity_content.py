from graph_db import GraphAccessor

graph_db = GraphAccessor()

def categorize_entity(entity_id: int) -> str:
    """
    Categorize the entity based on its content
    """
    return "unknown"

def get_full_text(entity_id: int) -> str:
    """
    Get the full text of the entity
    """
    return "full text"
from enrichment.llms import analysis_llm
from graph_db import GraphAccessor

from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.output_parsers import PydanticOutputParser

from typing import Function, List

from core_ops import EnrichmentCoreOps

def entity_retriever(entity_id: str, graph_db: GraphAccessor) -> list[str]:
    """
    Retrieve the entity description from the database.
    """
    query = "SELECT entity_detail FROM entities WHERE entity_id = %s;"
    result = graph_db.exec_sql(query, (entity_id,))
    
    if result:
        return [r[0] for r in result[0]]
    return None

class AssessmentOps(EnrichmentCoreOps):
    """
    This class creates an annotation over entitities, with
    respect to an *assessment question*
    """
    
    def __init__(self, prompt: str, budget: int = 1000, source_retriever: Function[str,str] = None):
        super().__init__(budget, [], [source_retriever])
        self.llm = analysis_llm
        self.prompt = prompt
        self.graph_accessor = GraphAccessor()
        
    def enrich_data(self, aux_data_providers = [], aux_data = []) -> dict:
        return super().enrich_data(aux_data_providers, aux_data)
    
    def est_cost(self, aux_data_providers = [], aux_data = []) -> int:
        return super().est_cost(aux_data_providers, aux_data)
    
    def _validate_data(self) -> bool:
        """
        Validate the given data.
        """
        # Placeholder for validation logic
        return True
    def _validate_results(self, results) -> bool:
        """
        Validate the results.
        """
        # Placeholder for validation logic
        return True    
    
# TODO: AssociateOps-
    
def entity_annotator(entity_id: str, expression: AssessmentOps):
    """
    Annotate the entity with respect to the question.
    """
    descriptions = entity_retriever(entity_id)
    if len(descriptions) == 0:
        return None
    
    for desc in descriptions:
        # Truncate the text to fit within the token limit
        #desc = truncate_text_to_token_limit(desc, 4096)
        
        # Create the prompt
        prompt = expression.prompt.format(
            entity_id=entity_id,
            entity_description=desc,
            question=expression.prompt
        )
        # Get the result from the LLM
        result = expression.llm(prompt)
        
        # Parse the result -- TODO, make this answer-or-none
        parser = StrOutputParser()
        parsed_result = parser.parse(result)
        # Validate the result
        if not expression._validate_results(parsed_result):
            raise ValueError("Invalid result")
        
        # Store the result in the database
        expression.graph_accessor.add_tag_to_entity(entity_id, parsed_result)


    
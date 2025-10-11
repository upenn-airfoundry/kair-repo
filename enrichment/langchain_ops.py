from enrichment.llms import get_analysis_llm
from backend.graph_db import GraphAccessor

from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.output_parsers import PydanticOutputParser

from typing import List, Dict, Any, Callable as Fun, Optional

from enrichment.core_ops import EnrichmentCoreOps
from prompts.llm_prompts import DocumentPrompts

def entity_retriever(entity_id: str, graph_db: GraphAccessor) -> list[str]:
    """
    Retrieve the entity description from the database.
    """
    query = "SELECT entity_detail FROM entities WHERE entity_id = %s;"
    result = graph_db.exec_sql(query, (entity_id,))
    
    if result:
        return [r[0] for r in result[0]]
    return []

class AssessmentOps(EnrichmentCoreOps):
    """
    This class creates an annotation over entitities, with
    respect to an *assessment question*
    """
    
    def __init__(self, prompt: str, tag: str, budget: int = 1000, source_retriever: Fun[str,str] = None):
        super().__init__(budget, [], [source_retriever])
        self.llm = get_analysis_llm()
        self.tag = tag
        self.prompt = prompt
        self.graph_accessor = GraphAccessor()
        
    def enrich_data(self, aux_data_providers = [], aux_data = []) -> dict:
        """
        Given a JSON descriptor of an entity, apply the prompt

        Args:
            aux_data_providers (list, optional): Directly provided data. Defaults to [].
            aux_data (list, optional): _description_. Defaults to [].

        Returns:
            dict: _description_
        """
        result = DocumentPrompts.answer_from_summary(aux_data_providers[0], self.prompt)
        
        if (result is None or result.lower().strip() == 'none'):
            return {}

        # Store the result in the database
        # self.graph_accessor.add_tag_to_entity(self.tag, result)
        return {self.tag: result}
        # return super().enrich_data(aux_data_providers, aux_data)
        
    
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
        expression.graph_accessor.add_or_update_tag(entity_id, parsed_result)


    
import logging
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder  # needed for agent prompt placeholders
from langchain.schema.output_parser import StrOutputParser
import requests

from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Literal, Tuple, Union, Any, Dict, cast
import difflib
from datetime import datetime

from enrichment.llms import get_agentic_llm, get_structured_agentic_llm

# Add the new Pydantic models for learning resources
class LearningResource(BaseModel):
    """A learning resource related to a specific topic."""
    title: str = Field(..., description="The title of the learning resource.")
    rationale: str = Field(..., description="A brief explanation of why this resource is relevant and useful.")
    url: str = Field(..., description="The URL of the learning resource.")
    open_access_pdf: Optional[str] = Field(None, description="The URL of the open-access PDF version of the resource, if available.")
    
class LearningResourceList(BaseModel):
    """A list of learning resources."""
    resources: List[LearningResource]


# Pydantic models for generating a structured solution plan
class PotentialSource(BaseModel):
    """Describes a potential source for acquiring a piece of data."""
    source_description: str = Field(..., description="A description of the potential source of data (e.g., a specific API, a web search, a database query).")
    required_inputs: str = Field(..., description="The inputs that this source requires to function.")
    # mcp_request: Optional[str] = Field(None, description="If the source is a known MCP (Meta-Cognitive Primitives) call, specify the exact request format.")

class TaskOutput(BaseModel):
    """Defines a single output field for a task."""
    name: str = Field(..., description="The name of the output field.")
    datatype: str = Field(..., description="The expected data type of the output (e.g., string, list, number).")
    description: str = Field(..., description="A clear description of what this output represents.")
    importance: str = Field(..., description="The importance of this output to the overall task (e.g., 'critical', 'high', 'medium', 'low').")
    ranking_means: str = Field(..., description="The method for choosing or ranking multiple potential values for this output.")
    potential_sources: List[PotentialSource] = Field(..., description="A list of potential sources to obtain the data for this output.")

class SolutionTask(BaseModel):
    """A single, well-defined task within a larger solution plan."""
    description_and_goals: str = Field(..., description="A detailed description of the task and its specific objectives.")
    info_acquisition_strategy: str = Field(..., description="How to acquire the necessary information to complete the task: from human input, from searching, from looking up an entry in a database, from calling a tool, etc.")
    decision_strategy: str = Field(..., description="How to make decisions about the task: from human input, from ranking candidates on a metric (if so, specify the metric), from calling a tool, etc.")
    inputs: List[str] = Field(..., description="A list of inputs required (from the user or from prior tasks) to perform this task.")
    outputs: List[TaskOutput] = Field(..., description="A list of structured outputs that this task will produce.")
    evaluation_evidence: str = Field(..., description="The evidence and methods that will be used to evaluate or assess the success of this task.")
    revisiting_criteria: str = Field(..., description="Criteria that would trigger a return to a prior decision or task.")
    needs_user_clarification: bool = Field(..., description="Whether this task requires clarification from the user before proceeding.")
    can_be_single_sourced: bool = Field(..., description="Whether the fields can all be sourced from a single location (trying multiple alternate locations).")
    potential_sources: List[PotentialSource] = Field(..., description="A list of potential sources to obtain all the data for this task.")

class SolutionPlan(BaseModel):
    """A structured plan composed of a list of tasks to solve a user's request."""
    tasks: List[SolutionTask]

# -------------------------
# Generic structured LLM helpers
# -------------------------
def _coerce_pydantic(model_cls: type[BaseModel], raw: Any) -> BaseModel | None:
    """Attempt to coerce raw output (dict/BaseModel/obj with model_dump) into the target Pydantic model."""
    if isinstance(raw, model_cls):
        return raw
    if isinstance(raw, dict):
        try:
            return model_cls(**raw)
        except Exception:
            return None
    if hasattr(raw, "model_dump"):
        try:
            data = raw.model_dump()  # type: ignore[attr-defined]
            return model_cls(**data)
        except Exception:
            return None
    return None

def invoke_structured_with_retry(
    *,
    llm,
    prompt: ChatPromptTemplate,
    model_cls: type[BaseModel],
    inputs: Dict[str, Any],
    max_attempts: int = 2,
    repair_instruction: str | None = None,
) -> BaseModel | None:
    """Synchronously invoke a structured LLM with schema validation and optional repair retry."""
    if llm is None:
        return None
    structured_llm = llm.with_structured_output(model_cls)  # type: ignore[attr-defined]
    chain = prompt | structured_llm
    attempt = 0
    last_error = None
    while attempt < max_attempts:
        attempt += 1
        raw = chain.invoke(inputs)
        inst = _coerce_pydantic(model_cls, raw)
        if inst is not None:
            return inst
        last_error = f"Coercion failure attempt {attempt}"
        if attempt < max_attempts and repair_instruction:
            # Augment system message with repair guidance
            repair_msgs = []
            for m in prompt.messages:  # type: ignore[attr-defined]
                repair_msgs.append(m)
            repair_msgs.insert(0, ("system", repair_instruction + f" Previous error: {last_error}"))
            prompt = ChatPromptTemplate.from_messages(repair_msgs)
            chain = prompt | structured_llm
    return None

async def ainvoke_structured_with_retry(
    *,
    llm,
    prompt: ChatPromptTemplate,
    model_cls: type[BaseModel],
    inputs: Dict[str, Any],
    max_attempts: int = 2,
    repair_instruction: str | None = None,
) -> BaseModel | None:
    """Async version of invoke_structured_with_retry."""
    if llm is None:
        return None
    structured_llm = llm.with_structured_output(model_cls)  # type: ignore[attr-defined]
    chain = prompt | structured_llm
    attempt = 0
    last_error = None
    while attempt < max_attempts:
        attempt += 1
        raw = await chain.ainvoke(inputs)
        inst = _coerce_pydantic(model_cls, raw)
        if inst is not None:
            return inst
        last_error = f"Coercion failure attempt {attempt}"
        if attempt < max_attempts and repair_instruction:
            repair_msgs = []
            for m in prompt.messages:  # type: ignore[attr-defined]
                repair_msgs.append(m)
            repair_msgs.insert(0, ("system", repair_instruction + f" Previous error: {last_error}"))
            prompt = ChatPromptTemplate.from_messages(repair_msgs)
            chain = prompt | structured_llm
    return None


# Pydantic models for describing dependencies between tasks in a SolutionPlan
class TaskDependency(BaseModel):
    """Represents a single dependency between two tasks in a solution plan."""
    source_task_id: str = Field(..., description="The unique identifier of the source task that produces the data.")
    source_task_description: str = Field(..., description="The full 'description_and_goals' of the source task that produces the data.")
    dependent_task_id: str = Field(..., description="The unique identifier of the dependent task that consumes the data.")
    dependent_task_description: str = Field(..., description="The full 'description_and_goals' of the dependent task that consumes the data.")
    data_schema: str = Field(..., description="The schema of the data flowing from the source to the dependent task, formatted as 'field:type'.")
    data_flow_type: Literal["automatic", "gated by user feedback", "rethinking the previous task", "parent task-subtask"] = Field(..., description="The nature of the data flow between the tasks.")
    relationship_description: str = Field(..., description="A description of the dependency, including the criteria evaluated from the source task's output before the dependent task can proceed.")

class TaskDependencyList(BaseModel):
    """A list of dependencies between tasks."""
    dependencies: List[TaskDependency]

class PaperQuestionSpec(BaseModel):
    """
    Specification for answering a question using research papers/articles.
    """
    evaluation_prompt: str = Field(
        ...,
        description="A clear prompt to be evaluated against the content of papers/articles to answer the user's question."
    )
    outputs: List[TaskOutput] = Field(
        default_factory=list,
        description="Structured output fields expected from evaluating the prompt. Each has a name and datatype."
    )
    outputs_schema: str = Field(
        default="",
        description="Compact schema string like '(field:type, field2:type, ...)'. Derived from outputs if not explicitly provided."
    )

class UpstreamTaskContext(BaseModel):
    """Grouped upstream context per prior task."""
    title: str = Field(..., description="Title or description of the upstream task.")
    json_entities: List[Union[str, dict]] = Field(default_factory=list, description="JSON snippets produced by the task.")

class FleshOutPromptSpec(BaseModel):
    """Assembled prompt and whether the task needs user clarification."""
    prompt: str
    needs_user_clarification: bool = False

from backend.graph_db import GraphAccessor

import pandas as pd
import json

from enrichment.llms import (
    get_analysis_llm,
    get_better_llm,
    get_structured_analysis_llm,
    get_agentic_llm,
    mcp_client,  # use MCP client to call SemanticScholarSearch and PDFAnalyzer
)
from files.tables import sample_rows_to_string


def _patch_pydantic_schema_v1(schema: dict):
    """
    Patches a Pydantic v2 schema to be compatible with older parsers
    by copying '$defs' to 'definitions' if it exists.
    """
    if '$defs' in schema:
        schema['definitions'] = schema['$defs']
    # Some providers (e.g., Vertex AI function calling) ignore unsupported keys like
    # 'additionalProperties'. Strip them recursively to avoid noisy warnings.
    def _strip_keys(obj):
        if isinstance(obj, dict):
            obj.pop('additionalProperties', None)
            for v in obj.values():
                _strip_keys(v)
        elif isinstance(obj, list):
            for it in obj:
                _strip_keys(it)
    _strip_keys(schema)


# Define the Pydantic Model
class ConditionalAnswer(BaseModel):
    """Response containing an answer or 'none' if the information is not in the context."""
    answer: Union[str, Literal['none']] = Field(
        description="The answer to the question based on the context, or the exact string 'none' if the information is not found."
    )

# This Pydantic model defines the structure of content from a web page
class OutgoingLink(BaseModel):
    """An outgoing link from the web page."""
    url: str = Field(..., description="The URL of the outgoing link.")
    category: Optional[Literal[
        "organizational directory page for a person",
        "personal or professional homepage",
        "research lab page",
        "lab member directory",
        "CV or resume",
        "teaching page",
        "projects page",
        "publications page",
        "software page",
        "talks and keynotes page",
        "google scholar profile",
        "other"
    ]] = Field(
        None,
        description="The category of the outgoing link, if it can be determined. Must be one of the allowed web page categories."
    )

class WebPage(BaseModel):
    """Structured information about a web page."""
    category: Literal[
        "organizational directory page for a person",
        "personal or professional homepage",
        "research lab page",
        "lab members, students, postdocs, and visitors directory",
        "CV or resume",
        "teaching page",
        "projects page",
        "publications page",
        "software page",
        "talks and keynotes page",
        "other"
    ] = Field(..., description="The category of the web page.")
    outgoing_links: List[OutgoingLink] = Field(
        default_factory=list,
        description="A list of outgoing links from the web page, each with its URL and category."
    )

# This Pydantic model defines the structure of each faculty member's data.
# The docstrings and descriptions guide the language model in its extraction task.

class FacultyMember(BaseModel):
    """Information about a single faculty member."""
    name: str = Field(..., description="The full name of the faculty member.")
    titles_or_positions: Optional[List[str]] = Field(None, description="A list of the faculty member's titles or positions.")
    homepage: Optional[str] = Field(None, description="The URL of the faculty member's personal or lab homepage.")
    email: Optional[str] = Field(None, description="The email address of the faculty member.")
    phone: Optional[str] = Field(None, description="The phone number of the faculty member.")
    address: Optional[str] = Field(None, description="The physical office or mailing address of the faculty member.")
    affiliations: Optional[List[str]] = Field(None, description="A list of departments or centers the faculty member is affiliated with.")
    research_interests: Optional[List[str]] = Field(None, description="A list of the faculty member's research interests.")
    google_scholar: Optional[str] = Field(None, description="The URL of the faculty member's Google Scholar profile.")

class PersonOfInterest(BaseModel):
    biosketch: str = Field(..., description="A concise biosketch describing their background and career.")  
    expertise_and_research: str = Field(..., description="A paragraph describing their expertise and research interests.")  
    known_projects: str = Field(..., description="A paragraph listing known projects associated with the person.")

class FacultyList(BaseModel):
    """A list of faculty members."""
    faculty: List[FacultyMember]
    
    
class QueryClassification(BaseModel):
    query_class: Literal[
        "general_knowledge", 
        "info_about_an_expert", 
        "find_an_expert_for_a_topic",
        "learning_resources_or_technical_training", 
        "information_from_prior_work_like_papers_or_videos_or_articles", 
        "multi_step_planning_or_problem_solving", 
        "other"] = Field(..., description="The class of the query, chosen from the predefined categories.")
    task_summary: str = Field(..., description="A brief description of the task involved.")

class DocumentPrompts:
    @classmethod
    def answer_from_summary(cls, json_fragment, question):
        """
        Queries GPT-4o-mini with a question about a JSON fragment.

        Args:
            json_fragment (str): The JSON fragment as a string.
            question (str): The question to ask about the JSON data.

        Returns:
            str: The answer generated by GPT-4o-mini.
        """

        try:
            # Initialize the ChatOpenAI model, specifying gpt-4o-mini
            llm = get_analysis_llm()

            # Create a prompt template
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are an expert at extracting information from JSON data. If the context does not contain the information needed to answer the question, the value of the 'answer' field should be the exact string 'none'. Otherwise, provide the answer in the 'answer' field."),
                ("user", "Here is the JSON data, optionally comprising paper titles, abstracts, and lists of authors including their affiliations or biosketches:\n\n{json_fragment}\n\nQuestion: {question}\n\nAnswer:"),
                ("user", "Tip: Respond with a JSON object conforming to the ConditionalAnswer schema.")
            ])

            structured_llm = llm.with_structured_output(ConditionalAnswer) # type: ignore
            # Create a chain
            structured_chain = prompt | structured_llm# | StrOutputParser()

            # Invoke the chain
            response = structured_chain.invoke({"title": json_fragment['title'], "question": question, "json_fragment": json_fragment})

            return response.answer # type: ignore

        except Exception as e:
            return f"An error occurred: {e}"


    @classmethod
    def summarize_web_page(cls, content: str) -> str:
        """
        Use LangChain to summarize the content of a web page.
        """
        try:
            # Initialize the LLM (e.g., OpenAI GPT)
            llm = get_analysis_llm()

            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant that summarizes author biographical information from HTML content."),
                ("user", "Summarize the author info from the following HTML:\n\n{html}"),
            ])

            chain = prompt | llm | StrOutputParser() # type: ignore

            summary = chain.invoke({"html": content})
            return summary
        except Exception as e:
            print(f"Error summarizing web page content: {e}")
            return "Summary could not be generated."

    @classmethod
    def answer_yes_no(cls, question: str):
        """Boolean question to GPT-4o-mini.
        This function is used to ask a yes/no question to the LLM.

        Args:
            question (str): _description_

        Returns:
            str: Yes or No
        """
        llm = get_analysis_llm()
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a concise assistant. Respond to the following question with strictly 'Yes' or 'No'. No other words or punctuation."),
            ("user", "{question}")
        ])
        
        chain = prompt | llm | StrOutputParser() # type: ignore
        response = chain.invoke({"question": question})
        return response

    @classmethod
    def summarize_table(cls, df: pd.DataFrame) -> str:
        """
        Use LangChain to summarize the table schema and sampled rows.

        Args:
            df (pd.DataFrame): The DataFrame to summarize.

        Returns:
            str: The summary and description generated by LangChain.
        """
        # Extract schema
        schema = ", ".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])

        # Sample rows
        sample_rows = sample_rows_to_string(df)

        # Combine schema and sample rows into a context
        context = f"Schema: {schema}\n\nSample Rows:\n{sample_rows}"

        # Initialize the GPT model
        llm = get_analysis_llm()

        # Create a prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert data analyst. Summarize the table schema and sample rows."),
            ("user", "Here is the table information:\n\n{context}\n\nPlease provide a summary and description.")
        ])

        # Create the LangChain chain
        chain = prompt | llm | StrOutputParser() # type: ignore

        # Run the chain with the context
        response = chain.invoke({"context": context})

        return response

    @classmethod
    def extract_faculty_from_html(cls, html_content: str) -> dict:
        """
        Parses HTML content to extract a list of faculty members.

        Args:
            html_content: The HTML of the faculty directory page as a string.

        Returns:
            A dictionary containing the extracted list of faculty members.
        """
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", "You are an expert at extracting information from HTML documents and structuring it in JSON."),
                ("human", 
                """
                Please extract all faculty members from the following HTML content. 
                
                **Input Description:**
                The provided text is the raw HTML content of a university faculty directory page.
                Each faculty member's information is usually contained within a parent `<div>` element or a `<tr>` row element.
                Look for common class names like 'faculty-member', 'person-profile', 'directory-entry', or similar patterns.
                Within each person's section, you will find their name (often in a heading tag like `<h2>` or `<h3>`), 
                their title, contact information (email, phone), and links to their homepage, profile page, or publications.
                Their name may have a hyperlink to their personal or lab homepage, and they may have a Google Scholar profile link,
                which can be determined by looking at the URL.
                
                Extract a list of all faculty members you can find in the provided HTML.
                
                **HTML Content:**
                ```html
                {html_content}
                ```
                """
                ),
            ]
        )
        # extraction_chain = create_structured_output_runnable(
        #     output_schema=FacultyList, 
        #     llm=analysis_llm, 
        #     prompt=prompt_template
        # )
        # Use with_structured_output to create the structured LLM
        structured_llm = get_structured_analysis_llm().with_structured_output(FacultyList)
        extraction_chain = prompt_template | structured_llm
        # Run the extraction chain on the text content.
        extracted_data = extraction_chain.invoke({"html_content": html_content})
        if extracted_data is not None:
            ret_data = extracted_data.model_dump() # type: ignore
        else:
            ret_data = {"faculty": []}

        return ret_data

    @classmethod
    def get_page_info(cls, html_content: str, name: str) -> dict:
        """
        Parses HTML content that is some kind of researcher, lab, project, or team page.

        Args:
            html_content: The HTML of the faculty directory page as a string.

        Returns:
            A dictionary containing the extracted content.
        """
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", "You are an expert at extracting information from HTML documents and structuring it in JSON."),
                ("human", 
                """
                Please categorize from the following HTML content. If the page is related to or for a person, it must mention their name, which is """ + name + """.
                
                **Input Description:**
                The provided text is the raw HTML content of a web page representing info about a researcher named """ +
                name +
                """, or their lab, or their research projects, 
                or their research team; or a list of publications, courses, or software.
                The page is likely to also link to other related pages, of one of these types.
                
                Categorize the page as one of the following:
                - organizational directory page for """ + name +""", which must mention """ + name + """
                - personal or professional homepage for """ + name +""", which must mention """ + name + """
                - research lab page for  for """ + name + """'s lab, which must mention """ + name + """
                - a directory of additional lab members, students, postdocs, or visitors for """ + name + """'s lab, which must mention """ + name + """
                - CV or resume, which must mention """ + name + """
                - teaching page, which must mention """ + name + """ and not just be an organizational teaching page
                - projects page, which must mention """ + name + """ and not just be an organizational research page
                - publications page, which must mention """ + name + """ and not just be an organizational publications page
                - software page, which must mention """ + name + """ and not just be an organizational publications page
                - talks and keynotes page, which must mention """ + name + """ and not just be an organizational publications page
                - other
                
                If the page has outgoing links, extract each link and categorize it as one of the following:
                - organizational directory page for a person
                - personal or professional homepage
                - research lab page
                - lab member directory
                - CV or resume
                - teaching page
                - projects page
                - publications page
                - software page
                - talks and keynotes page
                - google scholar profile
                - other
                
                **HTML Content:**
                ```html
                {html_content}
                ```
                """
                ),
            ]
        )

        structured_llm = get_better_llm().with_structured_output(WebPage)
        extraction_chain = prompt_template | structured_llm
        # Run the extraction chain on the text content.
        extracted_data = extraction_chain.invoke({"html_content": html_content})
        
        # Use LLM to verify the HTML content is about the person named "name"
        verification_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at verifying if a web page is about a specific person."),
            ("user", "Does the following HTML content clearly relate to the person named '{name}'? Respond strictly with 'Yes' or 'No'.\n\nHTML Content:\n{html_content}")
        ])
        verification_chain = verification_prompt | get_analysis_llm() | StrOutputParser() # type: ignore
        verification_result = verification_chain.invoke({"html_content": html_content, "name": name}).strip().lower()
        if verification_result != "yes":
            return {}
        
        if extracted_data is not None:
            ret_data = extracted_data.model_dump() # type: ignore
        else:
            ret_data = {}

        return ret_data

    @classmethod
    def is_about(cls, url: str, name: str) -> bool:
        """
        Checks if the URL is about the person with the given name.  Currently uses substring as opposed to LLM.

        Args:
            url (str): The URL to check.
            name (str): The name of the person.

        Returns:
            bool: True if the URL is about the person, False otherwise.
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            page_content = response.text
            count = 0
            for subname in name.split(' '):
                if subname.lower() in page_content.lower():
                    count += 1
                    
            return count >= len(name.split(' ')) / 2 and count > 1  # At least half of the name parts should be present in the content
        except Exception as e:
            page_content = ""
            return False

    @classmethod
    def classify_json(cls, paper_json: dict) -> str:
        """
        Classifies a paper's description (arxiv format) into a short category descriptor using an LLM.

        Args:
            paper_json (dict): Dictionary containing arxiv paper fields (id, journal-ref, authors, abstract, etc.)

        Returns:
            str: A short category descriptor for the paper.
        """
        class PaperCategory(BaseModel):
            """A short category descriptor for the paper."""
            category: str = Field(..., description="A concise, few-word category for the paper (e.g., 'machine learning', 'quantum physics', 'algebraic geometry').")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at classifying academic papers. Given a paper's metadata and abstract, generate a concise, few-word category descriptor for the paper. Respond only with the category string."),
            ("user", "Paper metadata:\n\n{paper_json}\n\nCategory:")
        ])

        structured_llm = get_analysis_llm().with_structured_output(PaperCategory) # type: ignore
        chain = prompt | structured_llm
        result = chain.invoke({"paper_json": paper_json})
        return result.category # type: ignore
    
    
class TablePrompts:
    @classmethod
    def describe_table(cls, name: str, df: pd.DataFrame) -> str:
        """
        Use LangChain to generate a textual description of a table based on its schema and sample rows.

        Args:
            df (pd.DataFrame): The DataFrame to describe.

        Returns:
            str: The textual description of the table generated by GPT.
        """
        # Extract schema
        schema = ", ".join([f"{col} {cls._get_sql_type(dtype)}" for col, dtype in zip(df.columns, df.dtypes)])

        # Sample rows
        sample_size = min(5, len(df))  # Limit to 5 rows for brevity
        sampled_rows = df.sample(n=sample_size, random_state=42).to_string(index=False, header=False)

        # Combine schema and sample rows into a context
        context = f"Schema: {name}({schema})\n\nSample Rows:\n{sampled_rows}"

        # Initialize the GPT model
        llm = get_analysis_llm()

        # Create a prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert data analyst. Summarize the table schema and sample rows."),
            ("user", "Here is the table information:\n\n{context}\n\nPlease provide a summary and description of the table.")
        ])

        # Create the LangChain chain
        chain = prompt | llm | StrOutputParser()

        # Run the chain with the context
        response = chain.invoke({"context": context})

        return response

    @classmethod
    def _get_sql_type(cls, dtype: Any) -> str:
        """
        Map Pandas data types to SQL data types.

        Args:
            dtype (pd.api.types.DtypeObj): The Pandas data type.

        Returns:
            str: The corresponding SQL data type.
        """
        if pd.api.types.is_integer_dtype(dtype):
            return "INTEGER"
        elif pd.api.types.is_float_dtype(dtype):
            return "DOUBLE PRECISION"
        elif pd.api.types.is_bool_dtype(dtype):
            return "BOOLEAN"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            return "TIMESTAMP"
        else:
            return "TEXT"

class WebPrompts:
    @classmethod
    async def find_learning_resources(cls, topic: str) -> LearningResourceList:
        """
        Finds learning resources for a given topic, with support for tool calls.
        """
        # Build and escape the schema for safe inclusion in a PromptTemplate
        schema_dict = LearningResourceList.model_json_schema()
        _patch_pydantic_schema_v1(schema_dict)
        schema_str = json.dumps(schema_dict, indent=2)
        escaped_schema_str = schema_str.replace("{", "{{").replace("}", "}}")

        # Tool-calling friendly prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an expert at finding high-quality learning resources. "
             "You have tools available, including a Semantic Scholar search tool. Please prefer open access resources when possible, and ask Semantic Scholar for those. "
             "Always call at least one tool to gather evidence before answering. "
             "After gathering information, return a single JSON object that strictly conforms to this schema:\n"
             f"```json\n{escaped_schema_str}\n```"),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = await get_agentic_llm(prompt=prompt)
        if agent is None:
            return LearningResourceList(resources=[])

        # Invoke the agent; provide chat_history if you have it, else empty
        response = await agent.ainvoke({
            "input": f"Find learning resources for: {topic}",
            "chat_history": []
        })

        try:
            final_output_str = response.get("output", "").strip()
            if final_output_str.startswith("```json"):
                final_output_str = final_output_str[7:]
            if final_output_str.endswith("```"):
                final_output_str = final_output_str[:-3]
            parsed = json.loads(final_output_str) if final_output_str else {"resources": []}
            return LearningResourceList(**parsed)
        except Exception as e:
            logging.error(f"Failed to parse agent output: {e}")
            return LearningResourceList(resources=[])

    @classmethod
    def format_resources_as_markdown(cls, resource_list: LearningResourceList) -> str:
        """
        Formats a list of learning resources into a Markdown table.

        Args:
            resource_list (LearningResourceList): The list of learning resources.

        Returns:
            str: A string containing the Markdown formatted table.
        """
        if not resource_list or not resource_list.resources:
            return "No learning resources were found."

        header = "| Title | Rationale | URL |\n"
        separator = "|---|---|---|\n"
        
        rows = []
        for resource in resource_list.resources:
            # Escape pipe characters to prevent breaking the table format
            title = resource.title.replace('|', '\\|')
            rationale = resource.rationale.replace('|', '\\|')
            # Format URL as a clickable link in Markdown
            url_link = f"[{resource.url}]({resource.url})"
            rows.append(f"| {title} | {rationale} | {url_link} |")
            
        return header + separator + "\n".join(rows)

    @classmethod
    def answer_from_summary(cls, json_fragment, question):
        """
        Queries GPT-4o-mini with a question about a JSON fragment.

        Args:
            json_fragment (str): The JSON fragment as a string.
            question (str): The question to ask about the JSON data.

        Returns:
            str: The answer generated by GPT-4o-mini.
        """

        try:
            # Initialize the ChatOpenAI model, specifying gpt-4o-mini
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0) # gpt-4o-preview is the correct model name.

            # Create a prompt template
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are an expert at extracting information from JSON data."),
                ("user", "Here is the JSON data, optionally comprising paper titles, abstracts, and lists of authors including their affiliations or biosketches:\n\n{json_fragment}\n\nQuestion: {question}\n\nAnswer:")
            ])

            # Create a chain
            chain = prompt | llm | StrOutputParser()

            # Invoke the chain
            answer = chain.invoke({"title": json_fragment['title'], "question": question, "json_fragment": json_fragment})

            return answer

        except Exception as e:
            return f"An error occurred: {e}"

    @classmethod
    def summarize_web_page(cls, content: str) -> str:
        """
        Use LangChain to summarize the content of a web page.
        """
        try:
            # Initialize the LLM (e.g., OpenAI GPT)
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant that summarizes author biographical information from HTML content."),
                ("user", "Summarize the author info from the following HTML:\n\n{html}"),
            ])

            chain = prompt | llm | StrOutputParser()

            summary = chain.invoke({"html": content})
            return summary
        except Exception as e:
            print(f"Error summarizing web page content: {e}")
            return "Summary could not be generated."

def get_current_year() -> int:
    """
    Gets the current year.
    """
    return datetime.utcnow().year

class ExpertBiosketch(BaseModel):
    """
    Structured biosketch for an expert.
    """
    name: Optional[str] = Field(default=None, description="Expert's full name.")
    organization: Optional[str] = Field(default=None, description="Primary affiliation or organization.")
    headshot_url: Optional[str] = Field(default=None, description="URL to a headshot/photo if available.")
    scholar_id: Optional[str] = Field(default=None, description="Google Scholar ID if available.")
    biosketch: str = Field(..., description="A concise narrative biographical sketch.")
    education_and_experience: List[str] = Field(
        default_factory=list,
        description="Education and work experience; include leadership/management roles."
    )
    major_research_projects_and_entrepreneurship: List[str] = Field(
        default_factory=list,
        description="Major research projects and entrepreneurship activities."
    )
    honors_and_awards: List[str] = Field(
        default_factory=list,
        description="Honors, awards, fellowships."
    )
    expertise_and_contributions: List[str] = Field(
        default_factory=list,
        description="Areas of expertise and major contributions."
    )
    recent_publications_or_products: List[str] = Field(
        default_factory=list,
        description="Recent publications, software, datasets, or products. Please include the title, authors, venue, and year."
    )
    all_articles: List[Any] = Field(
        default_factory=list,
        description="All articles found during the search."
    )
# -------------------------
# Utilities and new helpers
# -------------------------

# Validate an image URL via a fast HEAD request.
def _valid_image_url(url: Optional[str]) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        if 200 <= r.status_code < 400:
            ctype = r.headers.get("Content-Type", "")
            return isinstance(ctype, str) and ctype.lower().startswith("image")
        return False
    except Exception:
        return False

# Normalized call to a registered LangChain Tool (via MCP adapter).
async def _lc_tool_call(tool_name: str, args: dict) -> Any:
    """Call a registered LangChain Tool by name using normal LangChain APIs.
    Returns parsed JSON if possible, else raw output.
    Assumes `mcp_client.get_tools()` is available in this module.
    """
    try:
        tools = await mcp_client.get_tools()  # type: ignore[name-defined]
        target = None
        for t in tools:
            name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
            if name == tool_name:
                target = t
                break
        if target is None:
            logging.warning(f"LangChain tool not found: {tool_name}")
            return {}
        if hasattr(target, "ainvoke"):
            resp = await target.ainvoke(args)  # type: ignore[attr-defined]
        elif hasattr(target, "invoke"):
            resp = target.invoke(args)  # type: ignore[attr-defined]
        else:
            logging.warning(f"Tool {tool_name} has no invoke/ainvoke")
            return {}

        if isinstance(resp, str):
            s = resp.strip()
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    return json.loads(s)
                except Exception:
                    return s
            return s
        if isinstance(resp, dict) and "content" in resp:
            c = resp["content"]
            if isinstance(c, str):
                try:
                    return json.loads(c)
                except Exception:
                    return c
            return c
        return resp
    except Exception as e:
        logging.warning(f"_lc_tool_call failed for {tool_name}: {e}")
        return {}

async def fetch_recent_publications_via_scholar(
    name: str,
    organization: Optional[str] = None,
    *,
    max_items: int = 20,
    since_year: Optional[int] = None,
    locale: str = "en"
) -> Tuple[Optional[str], List[str], List[Dict[str, Any]]]:
    """Use SearchAPI Google Scholar tools to fetch recent publications for a person.
    
    Returns a list of formatted strings like "YYYY — Title — URL".
    """
    def _pick_profile(profiles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not profiles:
            return None
        if organization:
            org = organization.lower()
            for p in profiles:
                aff = p.get("affiliations") or p.get("affiliation") or ""
                if isinstance(aff, list):
                    aff = " ".join(map(str, aff))
                if isinstance(aff, str) and org in aff.lower():
                    return p
        return profiles[0]

    # 1) Find candidate profiles by name
    profiles_res = await _lc_tool_call("search_google_scholar_profiles", {"author_name": name, "num": "10", "hl": locale})
    profiles: List[Dict[str, Any]] = []
    if isinstance(profiles_res, dict):
        profiles = profiles_res.get("profiles") or profiles_res.get("results") or []
    elif isinstance(profiles_res, list):
        profiles = profiles_res

    chosen = _pick_profile(profiles)
    if not isinstance(chosen, dict):
        return None, [], []
    
    author_id = chosen.get("author_id") or chosen.get("scholar_id") or chosen.get("id")
    if not author_id:
        return None, [], []

    # 2) Fetch publications for that author
    pubs_res = await _lc_tool_call(
        "search_google_scholar_publications",
        # {"author_id": str(author_id), "num": str(max_items if max_items > 0 else 0), "page": "1", "hl": locale}
        {"author_id": str(author_id), "num": str(0), "page": "1", "hl": locale}
    )
    articles: List[Dict[str, Any]] = []
    if isinstance(pubs_res, dict):
        articles = pubs_res.get("articles") or pubs_res.get("publications") or pubs_res.get("results") or []
    elif isinstance(pubs_res, list):
        articles = pubs_res

    items: List[str] = []
    for art in articles:
        try:
            y_raw = art.get("year") or art.get("publication_year")
            year = int(str(y_raw)[:4]) if y_raw is not None else None
        except Exception:
            year = None
        if since_year is not None and year is not None and year < since_year:
            continue
        
        # Skip the undated items
        if year is None:
            continue
        title = str(art.get("title") or "").strip()
        link = art.get("link") or art.get("url") or art.get("paper_url") or ""
        link = str(link).strip() if link else ""
        # authors = ", ".join(str(a) for a in art.get("authors", []))
        authors = str(art.get("authors") or "").strip()
        venue = str(art.get("venue") or art.get("publication") or art.get("publication_venue") or "").strip()
        if title:
            pretty = f"{str(year) if year else 'n.d.'} — {authors}: {title}. {venue}. " + (f" — [link]({link})" if link else "")
            items.append(pretty)
            if max_items > 0 and len(items) >= max_items:
                break
            
        items.sort(reverse=True)  # Newest first. Since it's a stable sort, we'll sort by year, then by citation count in desc order.
    return (author_id, items, articles)

async def fetch_publications_via_dblp(
    name: str,
    *,
    similarity_threshold: float = 0.85,
    max_items: int = 50,
) -> Tuple[Optional[str], List[str], List[Dict[str, Any]]]:
    """Use the DBLP MCP server to fetch publications for an author by name.

    Mirrors fetch_recent_publications_via_scholar by returning:
      (author_identifier_or_None, formatted_items, raw_publications)

    Formatted items are like: "YYYY — Authors: Title. Venue. — [link](URL)"
    """
    try:
        # DBLP: get publications for author with fuzzy matching (expects numeric types, not strings)
        res = await _lc_tool_call(
            "get_author_publications",
            {
                "author_name": name,
                "similarity_threshold": float(similarity_threshold),
                "max_results": int(max_items),
                "include_bibtex": False,
            },
        )
        pubs: List[Dict[str, Any]] = []
        if isinstance(res, dict):
            pubs = res.get("publications") or []
        elif isinstance(res, list):
            # Some adapters may return just the list
            pubs = res
        elif isinstance(res, str):
            # FastMCP text content from DBLP tool; parse into structured publications
            pubs = parse_dblp_text_publications(res)

        items: List[str] = []
        for p in pubs:
            try:
                year = p.get("year")
                year_i = int(str(year)[:4]) if year is not None else None
            except Exception:
                year_i = None
            title = str(p.get("title") or "").strip()
            authors_val = p.get("authors")
            if isinstance(authors_val, list):
                authors = ", ".join(str(a) for a in authors_val)
            else:
                authors = str(authors_val or "").strip()
            venue = str(p.get("venue") or p.get("journal") or p.get("booktitle") or p.get("publication") or "").strip()
            # Prefer DOI link, else 'ee' (electronic edition), else 'url'
            link = p.get("doi")
            if link:
                link = f"https://doi.org/{str(link).lstrip('doi:').strip()}"
            if not link:
                link = p.get("ee") or p.get("url") or ""
            link = str(link).strip() if link else ""
            if title:
                pretty = f"{str(year_i) if year_i else 'n.d.'} — {authors}: {title}. {venue}. " + (f" — [link]({link})" if link else "")
                items.append(pretty)
                if max_items > 0 and len(items) >= max_items:
                    break
        # Sort newest-first by year
        try:
            items.sort(reverse=True)
        except Exception:
            pass
        # DBLP tool doesn't provide a stable author id here; return None for identifier
        return None, items, pubs
    except Exception as e:
        logging.warning(f"fetch_publications_via_dblp failed: {e}")
        return None, [], []

def parse_dblp_text_publications(text: str) -> List[Dict[str, Any]]:
    """Parse plain-text DBLP tool output into a list of publication dicts.

    Expected format per entry:
      N. Title.
         Authors: A1, A2, ...
         Venue: Venue Name (YYYY)

    Returns a list of dicts with keys: title, authors (list[str]), venue (str), year (int|None).
    Gracefully skips incomplete entries.
    """
    try:
        import re as _re
        lines = [ln.rstrip() for ln in (text or "").splitlines()]
        # Drop header like "Found 50 publications for author ..." and blank lines
        # Find first numbered line
        pubs: List[Dict[str, Any]] = []
        i = 0
        n = len(lines)
        num_re = _re.compile(r"^\s*(\d+)\.\s+(.*)\s*$")
        authors_re = _re.compile(r"^\s*Authors:\s*(.*)\s*$")
        venue_re = _re.compile(r"^\s*Venue:\s*(.*?)(?:\s*\((\d{4})\))?\s*$")

        while i < n:
            m = num_re.match(lines[i])
            if not m:
                i += 1
                continue
            # Title line
            title = m.group(2).strip()
            # Title lines in sample end with a trailing period; trim it without harming abbreviations
            if title.endswith(".") and not title.endswith(".."):
                title = title[:-1].strip()

            # Look ahead for Authors and Venue
            i += 1
            authors_list: List[str] = []
            venue = ""
            year_val: Optional[int] = None

            # Consume up to the next numbered entry or end
            while i < n and not num_re.match(lines[i]):
                la = authors_re.match(lines[i])
                if la:
                    raw = la.group(1).strip()
                    # Split by comma, keeping numeric suffixes like "Jianjun Chen 0001" intact
                    authors_list = [a.strip() for a in raw.split(",") if a.strip()]
                    i += 1
                    continue
                lv = venue_re.match(lines[i])
                if lv:
                    venue = (lv.group(1) or "").strip()
                    y = lv.group(2)
                    if y and y.isdigit():
                        try:
                            year_val = int(y)
                        except Exception:
                            year_val = None
                    i += 1
                    continue
                # Skip blank or unrelated lines
                i += 1

            if title:
                pubs.append({
                    "title": title,
                    "authors": authors_list,
                    "venue": venue,
                    "year": year_val,
                })

        return pubs
    except Exception as e:
        logging.warning(f"parse_dblp_text_publications failed: {e}")
        return []

class MergeChoice(BaseModel):
    chosen_index: Optional[int] = Field(None, description="Index of the chosen candidate from 'candidates', or null if none match.")
    rationale: str = Field(..., description="Brief reasoning for the choice.")

def _normalized_title(s: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (s or "")).split())

async def merge_arxiv_with_dblp(
    scholar_articles: List[Dict[str, Any]],
    dblp_articles: List[Dict[str, Any]],
    *,
    max_candidates: int = 5,
    min_similarity: float = 0.7,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """For each Google Scholar article that is an arXiv preprint, try to merge with a final DBLP entry.

    Strategy:
      - For each Scholar article with URL from arxiv.org, find up to N candidate DBLP entries by title similarity.
      - Ask an LLM to choose the best candidate that represents a final publication (conference/journal), not arXiv.
      - If chosen, replace the Scholar article's venue and URL with the DBLP venue and a final link (prefer DOI).
      - Return updated formatted items and the mutated scholar_articles list.
    """
    if not scholar_articles:
        return [], []

    # Precompute normalized titles for DBLP
    dblp_norm = [(_normalized_title(p.get("title", "")), p) for p in dblp_articles]

    updated_articles: List[Dict[str, Any]] = []
    for art in scholar_articles:
        try:
            art_copy = dict(art)
            link = art_copy.get("link") or art_copy.get("url") or art_copy.get("paper_url") or ""
            url = str(link).lower()
            if "arxiv.org" not in url:
                updated_articles.append(art_copy)
                continue

            title = str(art_copy.get("title") or "").strip()
            title_n = _normalized_title(title)
            # Score candidates by difflib ratio
            scored = []
            for norm_t, p in dblp_norm:
                if not norm_t:
                    continue
                sim = difflib.SequenceMatcher(None, title_n, norm_t).ratio()
                if sim >= min_similarity:
                    scored.append((sim, p))
            scored.sort(key=lambda x: x[0], reverse=True)
            candidates = [p for _, p in scored[:max_candidates]]

            if not candidates:
                updated_articles.append(art_copy)
                continue

            # Prepare concise candidate summary for LLM
            cand_view = []
            for idx, p in enumerate(candidates):
                cand_view.append({
                    "index": idx,
                    "title": p.get("title"),
                    "venue": p.get("venue") or p.get("journal") or p.get("booktitle"),
                    "year": p.get("year"),
                    "doi": p.get("doi"),
                    "ee": p.get("ee"),
                    "url": p.get("url"),
                    "type": p.get("type"),
                })

            llm = get_analysis_llm()
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are matching an arXiv preprint to its final published version. Choose a candidate only if it is clearly the same paper published in a conference or journal (not arXiv). Prefer venues like NeurIPS, ICML, ICLR, CVPR, ACL, major journals, etc. If unsure, choose null."),
                ("user", "ArXiv item:\nTitle: {title}\nAuthors: {authors}\nYear: {year}\nURL: {url}\n\nCandidates (from DBLP):\n{candidates}\n\nReturn JSON with fields: chosen_index (int or null) and rationale (string)."),
            ])
            structured = llm.with_structured_output(MergeChoice)  # type: ignore
            resp: MergeChoice = (prompt | structured).invoke({
                "title": art_copy.get("title"),
                "authors": art_copy.get("authors"),
                "year": art_copy.get("year"),
                "url": link,
                "candidates": json.dumps(cand_view, ensure_ascii=False, indent=2),
            }) # type: ignore

            if resp and resp.chosen_index is not None and 0 <= resp.chosen_index < len(candidates):
                chosen = candidates[resp.chosen_index]
                # Update venue and link to final
                venue = chosen.get("venue") or chosen.get("journal") or chosen.get("booktitle") or ""
                final_link = chosen.get("doi")
                if final_link:
                    final_link = f"https://doi.org/{str(final_link).lstrip('doi:').strip()}"
                if not final_link:
                    final_link = chosen.get("ee") or chosen.get("url") or link
                art_copy["venue"] = venue
                art_copy["publication"] = venue
                art_copy["link"] = final_link
                art_copy["url"] = final_link
            updated_articles.append(art_copy)
        except Exception:
            updated_articles.append(art)

    # Build pretty strings like Scholar fetch
    items: List[str] = []
    for art in updated_articles:
        try:
            y_raw = art.get("year") or art.get("publication_year")
            year = int(str(y_raw)[:4]) if y_raw is not None else None
        except Exception:
            year = None
        title = str(art.get("title") or "").strip()
        link = art.get("link") or art.get("url") or art.get("paper_url") or ""
        link = str(link).strip() if link else ""
        authors = str(art.get("authors") or "").strip()
        venue = str(art.get("venue") or art.get("publication") or art.get("publication_venue") or "").strip()
        if title:
            pretty = f"{str(year) if year else 'n.d.'} — {authors}: {title}. {venue}. " + (f" — [link]({link})" if link else "")
            items.append(pretty)
    try:
        items.sort(reverse=True)
    except Exception:
        pass
    return items, updated_articles

async def find_headshot_via_searchapi(name: str, organization: Optional[str] = None) -> Optional[str]:
    """Use SearchAPI image tools (via LangChain) to find a likely headshot URL for the person."""
    person_str = f"{name} {organization}".strip() if organization else name
    query = f"{person_str} headshot portrait"

    # Discover an image search tool
    try:
        tools = await mcp_client.get_tools()  # type: ignore[name-defined]
        toolnames = [getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None) for t in tools]
        toolnames = [t for t in toolnames if t]
    except Exception as e:
        logging.debug(f"find_headshot_via_searchapi: tool discovery failed: {e}")
        toolnames = []

    img_tool = None
    for tname in toolnames:
        tl = tname.lower()
        if "search_google_images" in tl or ("image" in tl and "google" in tl):
            img_tool = tname
            break

    if img_tool is None:
        # No tool found
        return None

    res = await _lc_tool_call(img_tool, {"q": query, "num": "10"})
    candidates: List[str] = []
    if isinstance(res, dict):
        imgs = res.get("images_results") or res.get("results") or res.get("images") or []
        for it in imgs:
            if isinstance(it, dict):
                u = it.get("original") or it.get("link") or it.get("image") or it.get("thumbnail")
                if isinstance(u, str):
                    candidates.append(u)
    elif isinstance(res, list):
        for it in res:
            if isinstance(it, dict):
                u = it.get("original") or it.get("link") or it.get("image") or it.get("thumbnail")
                if isinstance(u, str):
                    candidates.append(u)

    for cand in candidates:
        if _valid_image_url(cand):
            return cand
    return None

# -------------------------
# PeoplePrompts refactor
# -------------------------

class PeoplePrompts:
    @classmethod
    async def generate_expert_biosketch_from_prompt(cls, prompt_text: str) -> ExpertBiosketch:
        """
        Agentically call the LLM with structured output and return a fully populated ExpertBiosketch.
        Then:
          - Fetch publications from the last two years via Google Scholar (SearchAPI MCP) and add them.
          - If headshot_url is missing or invalid, use Google Images (via SearchAPI MCP) to find a suitable headshot URL.
        """
        agent = await get_structured_agentic_llm(ExpertBiosketch)
        schema = ExpertBiosketch.model_json_schema()
        schema_str = json.dumps(schema, indent=2).replace("{", "{{").replace("}", "}}")

        # Build a concrete input string for the agent
        instruction = (
            "You are a careful researcher. Given the user prompt about a person, extract a concise, factual expert biosketch. "
            "Populate ONLY the fields in the provided schema; if uncertain, omit that item. "
            "Use recent, publicly verifiable facts, starting from the person's CV or home page or public talks, as retrieved from a web search. "
            "Return a single JSON object that strictly conforms to the ExpertBiosketch schema:\n"
            f"```json\n{schema_str}\n```"
        )
        user_req_template = (
            "Fill fields: biosketch (narrative), education_and_experience (bullets; include leadership/management roles), "
            "major_research_projects_and_entrepreneurship (bullets), honors_and_awards (bullets), "
            "expertise_and_contributions (bullets), headshot_url (if available). "
            "Use tools like web search as well as Google Scholar search to get the most updated information.\n\n"
            "Prompt:\n{prompt_text}"
        )
        # Materialize the user text for agent input (not a template at this point)
        user_text_for_agent = user_req_template.format(prompt_text=prompt_text)
        agent_input = f"{instruction}\n\n{user_text_for_agent}"

        def _strip_fences(s: str) -> str:
            s = (s or "").strip()
            if s.startswith("```json"):
                s = s[len("```json"):].strip()
            if s.startswith("```"):
                s = s[len("```"):].strip()
            if s.endswith("```"):
                s = s[:-3].strip()
            return s

        def _to_str_list(v) -> List[str]:
            if not v:
                return []
            if isinstance(v, list):
                out: List[str] = []
                for it in v:
                    try:
                        out.append(it if isinstance(it, str) else json.dumps(it, ensure_ascii=False))
                    except Exception:
                        out.append(str(it))
                # Drop empties and duplicates preserving order
                seen, dedup = set(), []
                for s in out:
                    ss = s.strip()
                    if ss and ss not in seen:
                        seen.add(ss)
                        dedup.append(ss)
                return dedup
            return [str(v)]

        def _prune_to_model_keys(d: dict) -> dict:
            allowed = {
                "name",
                "organization",
                "headshot_url",
                "biosketch",
                "education_and_experience",
                "major_research_projects_and_entrepreneurship",
                "honors_and_awards",
                "expertise_and_contributions",
                "recent_publications_or_products",
            }
            return {k: v for k, v in (d or {}).items() if k in allowed}

        # 1) Try agent with tools for the core biosketch
        eb: Optional[ExpertBiosketch] = ExpertBiosketch(
            name=None,
            organization=None,
            headshot_url=None,
            biosketch=prompt_text.strip(),
            education_and_experience=[],
            major_research_projects_and_entrepreneurship=[],
            honors_and_awards=[],
            expertise_and_contributions=[],
            recent_publications_or_products=[],
        )
        if agent is not None:
            try:
                # Provide minimal context; agent_input already contains prompt_text
                result = await agent.ainvoke({"input": agent_input, "chat_history": []})  # type: ignore
                out = result.get("output", "") if isinstance(result, dict) else ""
                if out.startswith("Agent stopped"):
                    eb = None
                else:
                    data = json.loads(_strip_fences(out)) if out else {}
                    data = _prune_to_model_keys(data)

                    # Ensure required and normalize lists
                    data.setdefault("biosketch", prompt_text.strip())
                    data["education_and_experience"] = _to_str_list(data.get("education_and_experience"))
                    data["major_research_projects_and_entrepreneurship"] = _to_str_list(data.get("major_research_projects_and_entrepreneurship"))
                    data["honors_and_awards"] = _to_str_list(data.get("honors_and_awards"))
                    data["expertise_and_contributions"] = _to_str_list(data.get("expertise_and_contributions"))
                    data["recent_publications_or_products"] = _to_str_list(data.get("recent_publications_or_products"))

                    eb = ExpertBiosketch(**data)
            except Exception as e:
                logging.warning(f"Agentic biosketch failed; falling back to structured LLM. Error: {e}")
                eb = None
        else:
            eb = None

        # 2) Fallback: plain structured LLM (no tools)
        if eb is None:
            try:
                llm = get_better_llm()
                if llm is None:
                    raise RuntimeError("No LLM available")
                user_text = user_req_template.format(prompt_text=prompt_text)
                fallback_prompt = ChatPromptTemplate.from_messages([
                    ("system", instruction),
                    ("user", user_text),
                ])
                inst = await ainvoke_structured_with_retry(
                    llm=llm,
                    prompt=fallback_prompt,
                    model_cls=ExpertBiosketch,
                    inputs={},
                    max_attempts=2,
                    repair_instruction="If the previous JSON did not match the ExpertBiosketch schema, correct the JSON to match the schema exactly and return only JSON."
                )
                if inst is None:
                    raise RuntimeError("Structured LLM did not return a valid ExpertBiosketch after retries")
                eb = cast(ExpertBiosketch, inst)
                # Normalize lists and ensure biosketch
                eb.education_and_experience = _to_str_list(getattr(eb, "education_and_experience", []))
                eb.major_research_projects_and_entrepreneurship = _to_str_list(getattr(eb, "major_research_projects_and_entrepreneurship", []))
                eb.honors_and_awards = _to_str_list(getattr(eb, "honors_and_awards", []))
                eb.expertise_and_contributions = _to_str_list(getattr(eb, "expertise_and_contributions", []))
                eb.recent_publications_or_products = _to_str_list(getattr(eb, "recent_publications_or_products", []))
                if not (getattr(eb, "biosketch", "") or "").strip():
                    eb.biosketch = prompt_text.strip()
            except Exception as e:
                logging.error(f"Structured LLM biosketch fallback failed: {e}")
                return ExpertBiosketch(
                    name=None,
                    organization=None,
                    headshot_url=None,
                    biosketch=prompt_text.strip(),
                    education_and_experience=[],
                    major_research_projects_and_entrepreneurship=[],
                    honors_and_awards=[],
                    expertise_and_contributions=[],
                    recent_publications_or_products=[],
                )

        # Enrich with publications (last two years) and a headshot URL using helper functions
        if eb is None:
            return ExpertBiosketch(
                name=None,
                organization=None,
                headshot_url=None,
                biosketch=prompt_text.strip(),
                education_and_experience=[],
                major_research_projects_and_entrepreneurship=[],
                honors_and_awards=[],
                expertise_and_contributions=[],
                recent_publications_or_products=[],
            )

        # Publications enrichment
        try:
            current_year = datetime.utcnow().year
            (scholar_id, pubs, articles) = await fetch_recent_publications_via_scholar(
                name=(eb.name or '').strip() or prompt_text.strip(),
                organization=(eb.organization or '').strip() or None,
                max_items=20,
                since_year=current_year - 1,
            )
            if scholar_id:
                eb.scholar_id = scholar_id
            # Fetch DBLP publications and merge arXiv items to final venues when possible
            try:
                (_, dblp_items, dblp_articles) = await fetch_publications_via_dblp(
                    name=(eb.name or '').strip() or prompt_text.strip(),
                    similarity_threshold=0.85,
                    max_items=50,
                )
            except Exception:
                dblp_items, dblp_articles = [], []

            try:
                 merged_pretty, merged_articles = await merge_arxiv_with_dblp(articles or [], dblp_articles)
            except Exception:
                merged_pretty, merged_articles = pubs, (articles or [])

            eb.all_articles = merged_articles  # type: ignore
            if merged_pretty:
                existing = []
                merged_list = merged_pretty + [p for p in existing if p not in merged_pretty]
                eb.recent_publications_or_products = merged_list[:20]
        except Exception as e:
            logging.warning(f"Biosketch publications enrichment failed: {e}")

        # Headshot enrichment
        try:
            if getattr(eb, 'headshot_url', None) and getattr(eb, 'headshot_url', "").startswith("data://"):
                eb.headshot_url = None
            if not _valid_image_url(getattr(eb, 'headshot_url', None)):
                cand = await find_headshot_via_searchapi(
                    name=(eb.name or '').strip() or prompt_text.strip(),
                    organization=(eb.organization or '').strip() or None,
                )
                if cand:
                    eb.headshot_url = cand
        except Exception as e:
            logging.debug(f"Biosketch headshot enrichment skipped due to error: {e}")

        return eb
    
    @classmethod
    def persist_biosketch_to_graph(cls, graph: GraphAccessor, sketch: ExpertBiosketch) -> int:
        """Persist (upsert) an ExpertBiosketch to the DB using GraphAccessor.

        Upsert semantics:
        - Profile: Uses `add_entity_with_json` which now upserts on (entity_type, entity_url) so that a
            second persistence of the same Google Scholar profile URL updates JSON instead of creating a duplicate.
        - Papers: Uses `add_paper_full` which upserts on paper URL, updating metadata/JSON instead of duplicating.
        - Authors (if added elsewhere): `add_person` now prefers uniqueness by Google Scholar ID embedded in the URL.

        Steps:
            1) Upsert a google_scholar_profile entity with the full biosketch JSON.
            2) For each article in all_articles, upsert a paper entity (must have URL).
            3) Link profile -> paper with link_type='author' (link insert is idempotent via ON CONFLICT DO NOTHING).
            4) Annotate profile with entity_tags: name, biosketch, headshot_url (if present), and each item from
                    list fields (education_and_experience, major_research_projects_and_entrepreneurship, honors_and_awards,
                    expertise_and_contributions) as separate tag instances.

        Returns: profile entity_id.
        """
        # 1) Create google_scholar_profile core entity with JSON dump of the biosketch
        scholar_url: Optional[str] = None
        if getattr(sketch, "scholar_id", None):
            scholar_url = f"https://scholar.google.com/citations?user={sketch.scholar_id}&hl=en&oi=ao"

        profile_json = sketch.model_dump()  # full JSON
        profile_name = (sketch.name or "").strip() or "Google Scholar Profile"
        profile_desc = (sketch.organization or "").strip() or None

        profile_id = graph.add_entity_with_json(
            entity_type="google_scholar_profile",
            name=profile_name,
            description=profile_desc,
            json_content=profile_json,
            url=scholar_url,
        )

        # 4) Tag the profile
        try:
            if sketch.name:
                graph.add_or_update_tag(profile_id, "name", sketch.name, add_another=False)
            if getattr(sketch, "biosketch", None):
                graph.add_or_update_tag(profile_id, "biosketch", sketch.biosketch, add_another=False)
            if getattr(sketch, "headshot_url", None):
                graph.add_or_update_tag(profile_id, "headshot_url", sketch.headshot_url or "", add_another=False)

            # Lists: add each item as its own tag instance
            
            # Replace all educational experiences with updated ones, since there will be inexact matches
            # TODO: Consider asking the LLM to see if these have notably changed?
            graph.remove_tag(profile_id, "education")
            for item in (sketch.education_and_experience or []):
                if item and str(item).strip():
                    graph.add_or_update_tag(profile_id, "education", str(item).strip(), add_another=True)

            # TODO: Consider asking the LLM to see if these have notably changed?
            graph.remove_tag(profile_id, "research_projects")
            for item in (sketch.major_research_projects_and_entrepreneurship or []):
                if item and str(item).strip():
                    graph.add_or_update_tag(profile_id, "research_projects", str(item).strip(), add_another=True)

            # TODO: Consider asking the LLM to see if these have notably changed?
            graph.remove_tag(profile_id, "awards")
            for item in (sketch.honors_and_awards or []):
                if item and str(item).strip():
                    graph.add_or_update_tag(profile_id, "awards", str(item).strip(), add_another=True)

            graph.remove_tag(profile_id, "expertise")
            for item in (sketch.expertise_and_contributions or []):
                if item and str(item).strip():
                    graph.add_or_update_tag(profile_id, "expertise", str(item).strip(), add_another=True)
        except Exception as e:
            logging.warning(f"Failed tagging scholar profile {profile_id}: {e}")

        # 2) Create paper entities and 3) link them
        for art in getattr(sketch, "all_articles", []) or []:
            try:
                if not isinstance(art, dict):
                    continue
                title = str(art.get("title") or "").strip()
                if not title:
                    continue
                link = art.get("link") or art.get("url") or art.get("paper_url") or ""
                url = str(link).strip() if link else ""
                if not url:
                    # Require URL as per requirement "ensure URL is stored"; skip if missing.
                    continue
                # Normalize authors and venue/year
                authors_val = art.get("authors")
                if isinstance(authors_val, list):
                    authors = ", ".join(str(a) for a in authors_val)
                else:
                    authors = str(authors_val or "").strip()
                venue = str(art.get("venue") or art.get("publication") or art.get("publication_venue") or "").strip()
                try:
                    year = art.get("year")
                    year = int(str(year)[:4]) if year is not None else None
                except Exception:
                    year = None

                paper_id = graph.add_paper_full(
                    title=title,
                    url=url,
                    authors=authors or None,
                    venue=venue or None,
                    year=year,
                    extra_json=art,
                )
                if paper_id:
                    graph.add_entity_link(profile_id, paper_id, "author")
            except Exception as e:
                logging.warning(f"Failed to persist article for profile {profile_id}: {e}")

        return profile_id
    
    @classmethod
    def format_biosketch_as_markdown(cls, sketch: ExpertBiosketch) -> str:
        """
        Formats the ExpertBiosketch as a Markdown string.
        """
        lines = []
        if sketch.name:
            lines.append(f"## [{sketch.name}](https://scholar.google.com/citations?user={sketch.scholar_id}&hl=en&oi=ao)\n")
        if sketch.organization:
            lines.append(f"**Affiliation:** {sketch.organization}\n")
        if sketch.headshot_url and _valid_image_url(sketch.headshot_url):
            lines.append(f"![Headshot]({sketch.headshot_url})\n")
        lines.append(f"### Biosketch\n{sketch.biosketch}\n")
        
        if sketch.education_and_experience:
            lines.append("### Education and Experience")
            for item in sketch.education_and_experience:
                lines.append(f"- {item}")
            lines.append("")

        if sketch.major_research_projects_and_entrepreneurship:
            lines.append("### Major Projects and Activities")
            for item in sketch.major_research_projects_and_entrepreneurship:
                lines.append(f"- {item}")
            lines.append("")

        if sketch.honors_and_awards:
            lines.append("### Honors and Awards")
            for item in sketch.honors_and_awards:
                lines.append(f"- {item}")
            lines.append("")

        if sketch.expertise_and_contributions:
            lines.append("### Expertise and Contributions")
            for item in sketch.expertise_and_contributions:
                lines.append(f"- {item}")
            lines.append("")

        if sketch.recent_publications_or_products:
            lines.append("### Recent Publications or Products")
            for item in sketch.recent_publications_or_products:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)


    @classmethod
    def get_person_publications(cls, graph_accessor: GraphAccessor, name: str, organization: str, scholar_id: str) -> List[dict]:
        from crawl.web_fetch import scholar_search_gscholar_by_id
        """
        Uses Google Scholar and the LLM to generate a list of publications for a person.

        Args:
            name (str): The person's name.
            organization (str): The organization the person is affiliated with.
            scholar_id (Optional[str]): The Google Scholar ID of the person, if available.
            
        Returns:
            List[dict]: A list of publications, each represented as a dictionary with keys "title", "authors", "venue", "year", and "url".
        """

        if not scholar_id:
            return []

        # Use GraphAccessor to load author data by scholar_id, optionally filtering by name and organization
        author_data = graph_accessor.get_author_by_scholar_id(scholar_id)
        if not author_data or "articles" not in author_data:
            # Fetch profile if we don't have cached articles
            profile = scholar_search_gscholar_by_id(graph_accessor, scholar_id, [])
            if profile:
                if isinstance(profile, dict):
                    return profile.get("articles", []) or []
                if isinstance(profile, list):
                    return profile
                # Unknown type; fallback empty
                return []
        if author_data:
            if isinstance(author_data, dict):
                return author_data.get("articles", []) or []
            if isinstance(author_data, list):
                return author_data
        return []
    
    @classmethod
    def get_person_profile(cls, name: str, organization: str) -> dict:
        """
        Uses the LLM to generate a structured profile for a person, including a biosketch, expertise/research, and known projects.

        Args:
            name (str): The person's name.
            organization (str): The organization the person is affiliated with.

        Returns:
            dict: A dictionary with keys "biosketch", "expertise", "projects".
        """
        from prompts.llm_prompts import PersonOfInterest

        llm = get_better_llm()
        if llm is None:
            # Conservative fallback if LLM unavailable
            return {
                "biosketch": f"{name} at {organization}. (LLM unavailable; minimal profile.)",
                "expertise": "",
                "projects": ""
            }
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at summarizing academic and professional profiles. Respond with a structured output matching the PersonOfInterest schema."),
            ("user", 
                f"Summarize what is known about {name} at {organization} in three paragraphs:\n"
                "1. A concise biosketch describing their background and career.\n"
                "2. A paragraph describing their expertise and research interests.\n"
                "3. A paragraph describing their known projects or major contributions.\n"
                "Respond in clear, factual prose and use the PersonOfInterest schema."
            )
        ])
        # Use structured output
        inst = invoke_structured_with_retry(
            llm=llm,
            prompt=prompt,
            model_cls=PersonOfInterest,
            inputs={},
            max_attempts=2,
            repair_instruction="If your previous JSON did not match the PersonOfInterest schema, correct it and return only valid JSON."
        )
        if inst is None:
            poi = PersonOfInterest(biosketch=f"{name} at {organization}.", expertise_and_research="", known_projects="")
        else:
            poi = cast(PersonOfInterest, inst)
        return {
            "biosketch": poi.biosketch,
            "expertise": poi.expertise_and_research,
            "projects": poi.known_projects,
        }
        
    @classmethod
    def classify_query_and_summarize(cls, query: str) -> QueryClassification:
        # Use a fast LLM (e.g., Gemini Flash or GPT-3.5) with a structured output
        from enrichment.llms import get_analysis_llm
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Classify the following query and summarize the task. Respond with a JSON object matching the QueryClassification schema."),
            ("user", f"Query: {query}")
        ])
        base_llm = get_analysis_llm()
        if base_llm is None:
            # Fallback classification when analysis LLM unavailable
            return QueryClassification(
                query_class="general_knowledge",
                task_summary=f"{query[:200]}"
            )
        inst = invoke_structured_with_retry(
            llm=base_llm,
            prompt=prompt,
            model_cls=QueryClassification,
            inputs={"query": query},
            max_attempts=2,
            repair_instruction="If your previous JSON did not match the QueryClassification schema, correct it and return only valid JSON."
        )
        if inst is None:
            return QueryClassification(query_class="general_knowledge", task_summary=f"{query[:200]}")
        return cast(QueryClassification, inst)

class QueryPrompts:
    @classmethod
    def build_expanded_prompt(cls, system_profile: str, user_profile: dict, user_history: list, task_summary: str, user_prompt: str):
        history_str = ""
        for items in user_history[-5:]:
            prompt = items[0]
            response = items[1]
            history_str += f"User: {prompt}\nSystem: {response}\n"
            
        if len(history_str) == 0:
            context = (
                f"General instructions: {system_profile}\n"
                f"User expertise: {user_profile.get('expertise','')}\n"
                f"Projects and interests: {user_profile.get('projects','')}\n"
                f"Task summary: {task_summary}\n"
                f"Current query: {user_prompt}"
            )
        else:
            context = (
                f"General instructions: {system_profile}\n"
                f"User expertise: {user_profile.get('expertise','')}\n"
                f"Projects and interests: {user_profile.get('projects','')}\n"
                f"Task summary: {task_summary}\n"
                f"Recent history:\n{history_str}\n"
                f"Current query: {user_prompt}"
        )
        return context


    @classmethod
    def classify_query_and_summarize(cls,query: str) -> QueryClassification:
        # Use a fast LLM (e.g., Gemini Flash or GPT-3.5) with a structured output
        from enrichment.llms import get_analysis_llm
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Classify the following query and summarize the task. Respond with a JSON object matching the QueryClassification schema."),
            ("user", f"Query: {query}")
        ])
        base = get_analysis_llm()
        if base is None:
            return QueryClassification(query_class="general_knowledge", task_summary=query[:200])
        inst = invoke_structured_with_retry(
            llm=base,
            prompt=prompt,
            model_cls=QueryClassification,
            inputs={"query": query},
            max_attempts=2,
            repair_instruction="If your previous JSON did not match the QueryClassification schema, correct it and return only valid JSON."
        )
        if inst is None:
            return QueryClassification(query_class="general_knowledge", task_summary=query[:200])
        return cast(QueryClassification, inst)


class PlanningPrompts:
    @classmethod
    def generate_solution_plan(cls, user_request: str) -> SolutionPlan:
        """
        Generates a structured solution plan for a user's request.

        Args:
            user_request (str): The user's prompt or request.

        Returns:
            SolutionPlan: A Pydantic object containing a list of structured tasks.
        """
        llm = get_better_llm()
        if llm is None:
            return SolutionPlan(tasks=[])

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a master planner and problem solver. Your goal is to break down a complex user request into a series of concrete, actionable tasks. "
             "For each task, you must define its goals, inputs, and outputs. For each output, you must specify its structure and potential sources, including any known internal API (MCP) calls. "
             "You must also define how to evaluate the task's success and when to reconsider previous steps. "
             "Finally, indicate if a task requires user clarification. "
             "Respond with a JSON object that strictly conforms to the SolutionPlan schema."),
            ("user",
             "Please generate a detailed, structured solution plan for the following request:\n\n"
             "Request: \"{user_request}\"")
        ])

        inst = invoke_structured_with_retry(
            llm=llm,
            prompt=prompt,
            model_cls=SolutionPlan,
            inputs={"user_request": user_request},
            max_attempts=2,
            repair_instruction="If your previous JSON did not match the SolutionPlan schema, correct it and return only valid JSON."
        )
        return cast(SolutionPlan, inst) if inst is not None else SolutionPlan(tasks=[])

    @classmethod
    def determine_task_dependencies(cls, solution_plan: SolutionPlan) -> TaskDependencyList:
        """
        Analyzes a SolutionPlan to determine dependencies and dataflows between its tasks.

        Args:
            solution_plan (SolutionPlan): The plan containing the list of tasks.

        Returns:
            TaskDependencyList: A Pydantic object containing the list of identified dependencies.
        """
        llm = get_better_llm()
        if llm is None:
            return TaskDependencyList(dependencies=[])

        # Convert the plan to a string representation for the prompt
        plan_str = ""
        for i, task in enumerate(solution_plan.tasks):
            plan_str += f"--- Task {i+1} ---\n"
            plan_str += f"ID: task_{i}\n"
            plan_str += f"Description and Goals: {task.description_and_goals}\n"
            plan_str += f"Inputs: {', '.join(task.inputs)}\n"
            plan_str += f"Outputs: {', '.join([f'{o.name}:{o.datatype}' for o in task.outputs])}\n"
            plan_str += f"Evaluation Evidence: {task.evaluation_evidence}\n"
            plan_str += f"Revisiting Criteria: {task.revisiting_criteria}\n"
            plan_str += f"Needs User Clarification: {task.needs_user_clarification}\n\n"

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an expert system architect specializing in data flow analysis. Your task is to analyze a list of tasks and identify the dependencies between them. "
             "A task depends on another if it consumes one or more of its outputs as an input. "
             "For each dependency, you must determine the data schema being passed and the nature of the data flow. "
             "If a task's `revisiting_criteria` suggests a feedback loop to a prior task, model this as a 'rethinking the previous task' dependency. "
             "If a task's `decision_strategy` or `needs_user_clarification` flag indicates user input is required, the flow is 'gated by user feedback'. "
             "Otherwise, the flow is 'automatic'. "
             "The `relationship_description` should capture the evaluation criteria from the source task. "
             "Respond with a JSON object that strictly conforms to the TaskDependencyList schema."),
            ("user",
             "Based on the following solution plan, please identify all dependencies between the tasks:\n\n"
             "{solution_plan_str}")
        ])

        inst = invoke_structured_with_retry(
            llm=llm,
            prompt=prompt,
            model_cls=TaskDependencyList,
            inputs={"solution_plan_str": plan_str},
            max_attempts=2,
            repair_instruction="If your previous JSON did not match the TaskDependencyList schema, correct it and return only valid JSON."
        )
        return cast(TaskDependencyList, inst) if inst is not None else TaskDependencyList(dependencies=[])
    
    @classmethod
    def build_flesh_out_prompt(
        cls,
        *,
        task_name: str,
        task_description: str,
        task_schema: str = "",
        task_context: Optional[Union[str, dict]] = None,
        upstream_contexts: List[UpstreamTaskContext] = [],
    ) -> FleshOutPromptSpec:
        """
        Assemble the prompt used to flesh out a task and optionally include upstream JSON entities.
        If task_context looks like a SolutionTask, include outputs and execution guidance.
        """
        # Base prompt
        base = (task_description or "").strip() or (task_name or "").strip() or "Task"
        prompt_lines: List[str] = [base]
        needs_user = False

        # Parse optional structured task context (may be a SolutionTask)
        sol: Optional[SolutionTask] = None
        try:
            ctx_obj: Any = task_context
            if isinstance(ctx_obj, str):
                ctx_obj = json.loads(ctx_obj)
            if isinstance(ctx_obj, dict):
                try:
                    # Pydantic v2
                    sol = SolutionTask.model_validate(ctx_obj)  # type: ignore[attr-defined]
                except Exception:
                    # v1 fallback
                    sol = SolutionTask.parse_obj(ctx_obj)  # type: ignore
        except Exception:
            sol = None

        # If the context indicates clarification is needed, mark and return a short prompt
        if sol and getattr(sol, "needs_user_clarification", False):
            needs_user = True
            prompt_lines = [
                "This task needs further clarification from the user.",
                "",
                base,
                "",
                "Please provide more details."
            ]
            return FleshOutPromptSpec(prompt="\n".join(prompt_lines).strip(), needs_user_clarification=needs_user)

        # If we have a SolutionTask with description/goals, bias toward execution phrasing
        if sol and getattr(sol, "description_and_goals", None):
            prompt_lines = [f"Please try to execute the task: {sol.description_and_goals.strip()}", ""]

        # Include desired outputs if available
        outputs = getattr(sol, "outputs", None)
        if outputs:
            prompt_lines.append("The desired outputs are:")
            for o in outputs:
                try:
                    desc = getattr(o, "description", "") or ""
                    prompt_lines.append(f"- {o.name} ({o.datatype}): {desc}")
                except Exception:
                    continue
            prompt_lines.append("")

        # Global guidance
        prompt_lines.append(
            "If the task cannot be directly solved, please provide a more detailed plan or sub-tasks to achieve this task, "
            "considering the project context and user profile."
        )
        prompt_lines.append("")

        # Upstream JSON entities grouped by source task
        if upstream_contexts:
            prompt_lines.append(
                "This task depends on the outputs of prior tasks. The available information from those tasks is provided below as context:"
            )
            prompt_lines.append("")
            prompt_lines.append("--- BEGIN UPSTREAM DATA ---")
            for grp in upstream_contexts:
                title = grp.title or "Upstream task"
                prompt_lines.append(f"\n--- Data from upstream task: '{title}' ---")
                for js in grp.json_entities or []:
                    try:
                        if isinstance(js, (dict, list)):
                            prompt_lines.append(json.dumps(js, ensure_ascii=False))
                        else:
                            prompt_lines.append(str(js))
                    except Exception:
                        prompt_lines.append(str(js))
                prompt_lines.append("")
            prompt_lines.append("--- END UPSTREAM DATA ---")
            prompt_lines.append("")

        return FleshOutPromptSpec(prompt="\n".join(prompt_lines).strip(), needs_user_clarification=needs_user)
    
    @classmethod
    def extract_paper_question_spec(cls, user_request: str) -> "PaperQuestionSpec":
        """
        Given a user's question about research papers/articles, return:
          - evaluation_prompt: the concise prompt to evaluate against paper/article content;
          - outputs and outputs_schema: structured fields (name, datatype) expected in the answer.
        """
        try:
            llm = get_better_llm()
            if llm is None:
                # Conservative fallback
                return PaperQuestionSpec(
                    evaluation_prompt=user_request.strip(),
                    outputs=[],
                    outputs_schema="(title:string,answer:string,url:string)",
                )

            prompt = ChatPromptTemplate.from_messages([
                ("system",
                 "You design extraction specs for answering questions using research papers/articles. "
                 "Return a structured object with:\n"
                 "1) 'evaluation_prompt': a precise prompt to apply to the paper(s) to extract/compute the answer; "
                 "2) 'outputs': an array of fields with 'name' and 'datatype' (string, number, boolean, date, json, list[string], etc.); "
                 "3) optionally 'outputs_schema' as a compact string like '(field:type, field2:type)'. "
                 "Keep fields unambiguous and minimal."),
                ("user", "Question about papers/articles:\n{question}")
            ])

            inst = invoke_structured_with_retry(
                llm=llm,
                prompt=prompt,
                model_cls=PaperQuestionSpec,
                inputs={"question": user_request},
                max_attempts=2,
                repair_instruction="If your previous JSON did not match the PaperQuestionSpec schema, correct it and return only valid JSON."
            )
            if inst is None:
                raise ValueError("Unexpected return from structured_llm")
            spec = cast(PaperQuestionSpec, inst)

            # Derive outputs_schema if missing
            if not (spec.outputs_schema or "").strip():
                parts = []
                for o in (spec.outputs or []):
                    name = (o.name or "").strip()
                    dtype = (o.datatype or "string").strip()
                    if name:
                        parts.append(f"{name}:{dtype}")
                spec.outputs_schema = f"({', '.join(parts)})" if parts else "(answer:string,url:string)"
            return spec
        except Exception as e:
            logging.warning(f"extract_paper_question_spec failed: {e}")
            return PaperQuestionSpec(
                evaluation_prompt=user_request.strip(),
                outputs=[],
                outputs_schema="(title:string,answer:string,url:string)",
            )

    @classmethod
    async def execute_single_source_paper_tasks(cls, solution_plan: SolutionPlan) -> dict:
        import logging
        results: dict = {}

        # Discover tools
        try:
            tools = await mcp_client.get_tools()  # already awaited (good)
        except Exception as e:
            logging.error(f"Failed to list MCP tools: {e}")
            tools = []

        def find_search_tool_name() -> str | None:
            for t in tools:
                name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
                if name:
                    lname = name.lower()
                    if "semantic" in lname or "scholar" in lname or "paper" in lname or "search" in lname:
                        return name
            return None

        search_tool_name = find_search_tool_name()

        for idx, task in enumerate(solution_plan.tasks):
            if task.needs_user_clarification or not task.can_be_single_sourced:
                continue

            has_paper_source = any(_is_paper_source(ps.source_description) for ps in (task.potential_sources or []))
            if not has_paper_source:
                logging.info(f"[Plan] Task {idx} single-source is not a paper; cannot take action.")
                continue

            outputs_names = ", ".join(o.name for o in task.outputs) if task.outputs else ""
            query = task.description_and_goals.strip()
            if outputs_names:
                query = f"{query} {outputs_names}".strip()

            paper_url: str | None = None
            if search_tool_name:
                try:
                    search_args = {"query": query, "limit": 5}
                    # Attempt generic invoke; fallback to execute_tool or empty list
                    search_fn = getattr(mcp_client, "invoke", None)
                    if callable(search_fn):  # type: ignore[attr-defined]
                        search_results = await search_fn(search_tool_name, search_args)  # type: ignore
                    else:
                        exec_fn = getattr(mcp_client, "execute_tool", None)
                        if callable(exec_fn):
                            search_results = await exec_fn(search_tool_name, search_args)  # type: ignore
                        else:
                            search_results = []
                    items = []
                    if isinstance(search_results, dict) and "results" in search_results:
                        items = search_results["results"]
                    elif isinstance(search_results, list):
                        items = search_results
                    for item in items:
                        url = None
                        if isinstance(item, dict):
                            url = item.get("url") or item.get("pdfUrl") or item.get("paperUrl")
                        elif hasattr(item, "get"):
                            url = item.get("url", None)
                        if url:
                            paper_url = url
                            if url.lower().endswith(".pdf") or "pdf" in url.lower():
                                break
                except Exception as e:
                    logging.error(f"[Plan] Search tool '{search_tool_name}' failed: {e}")

            if not paper_url:
                logging.info(f"[Plan] No paper URL found for task {idx}")
                continue

            outputs_spec = []
            for o in (task.outputs or []):
                outputs_spec.append({
                    "name": o.name,
                    "goal": o.description or f"Extract {o.name}",
                    "type": _normalize_type(o.datatype),
                })

            try:
                analyzer_args = {"urls": [paper_url], "outputs": outputs_spec}
                index_fn = getattr(mcp_client, "invoke", None)
                if callable(index_fn):  # type: ignore[attr-defined]
                    analyzer_res = await index_fn("index_papers", analyzer_args)  # type: ignore
                else:
                    exec_fn = getattr(mcp_client, "execute_tool", None)
                    if callable(exec_fn):
                        analyzer_res = await exec_fn("index_papers", analyzer_args)  # type: ignore
                    else:
                        analyzer_res = {}
                url_map = analyzer_res.get("results", analyzer_res) if isinstance(analyzer_res, dict) else analyzer_res
                task_key = f"task_{idx}"
                if isinstance(url_map, dict) and paper_url in url_map:
                    results[task_key] = url_map[paper_url]
                else:
                    if isinstance(url_map, dict) and url_map:
                        first_val = next(iter(url_map.values()))
                        results[task_key] = first_val if isinstance(first_val, dict) else {}
                    else:
                        results[task_key] = {}
            except Exception as e:
                logging.error(f"[Plan] PDFAnalyzer index_papers failed for task {idx}: {e}")

        return results

def _is_paper_source(desc: str | None) -> bool:
    """Heuristic: does a potential source description refer to a paper/PDF?"""
    if not desc:
        return False
    s = desc.lower()
    return any(k in s for k in ("paper", "pdf", "arxiv", "doi", "journal", "conference"))

def _normalize_type(t: str | None) -> str:
    """Map arbitrary datatype strings to a small set supported by the PDF analyzer."""
    if not t:
        return "string"
    tl = t.lower()
    if "bool" in tl:
        return "boolean"
    if any(k in tl for k in ("int", "number", "float", "double")):
        return "number"
    if any(k in tl for k in ("json", "object", "array", "list", "dict")):
        return "json"
    if "date" in tl:
        return "date"
    return "string"

from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate

# NEW: Decision model for "requires human?" checks
class RequiresHumanDecision(BaseModel):
    requires_human: bool = Field(..., description="True if human input or feedback is needed; False if the task can proceed fully by LLM/tools.")
    rationale: str = Field(..., description="Brief rationale explaining the decision.")
    missing_inputs: Optional[List[str]] = Field(default=None, description="If human is required, list any missing or ambiguous inputs the human should provide.")

class DecisionPrompts:
    @classmethod
    async def requires_human(cls, *,
                             task_name: str,
                             task_description: str,
                             outputs_schema: str,
                             upstream_text: str,
                             downstream_needs_text: str) -> RequiresHumanDecision:
        """
        Ask a tool-capable LLM agent to determine if a task requires human input.
        Returns a structured RequiresHumanDecision object.
        """
        # Build JSON schema string for the agent to follow
        schema_dict = RequiresHumanDecision.model_json_schema()
        from prompts.llm_prompts import _patch_pydantic_schema_v1  # reuse helper
        _patch_pydantic_schema_v1(schema_dict)
        import json as _json
        schema_str = _json.dumps(schema_dict, indent=2).replace("{", "{{").replace("}", "}}")

        instruction = (
            "You are a planning/coordination assistant with tool access. "
            "Decide whether the current task requires human intervention or can be performed by the LLM (with tools). "
            "Use tools if needed to verify feasibility. "
            "Return a single JSON object that strictly conforms to the provided schema."
        )
        content = (
            f"{instruction}\n\n"
            f"Task:\n- Name: {task_name}\n- Description/Goals: {task_description}\n"
            f"- Desired Outputs Schema: {outputs_schema}\n\n"
            f"Available Upstream Information (summarized):\n{upstream_text or '(none)'}\n\n"
            f"Downstream Needs (dependent tasks expectations):\n{downstream_needs_text or '(none)'}\n\n"
            f"Schema:\n```json\n{schema_str}\n```"
        )

        agent = await get_agentic_llm()  # tool-capable agent
        if agent is None:
            return RequiresHumanDecision(requires_human=True, rationale="Tool agent unavailable", missing_inputs=None)  # conservative default

        try:
            resp = await agent.ainvoke({"input": content, "chat_history": []})
            out = resp.get("output", "").strip() if isinstance(resp, dict) else ""
            if out.startswith("```json"):
                out = out[7:]
            if out.endswith("```"):
                out = out[:-3]
            parsed = _json.loads(out) if out else {"requires_human": True, "rationale": "Empty agent output"}
            return RequiresHumanDecision(**parsed)
        except Exception as e:
            import logging as _lg
            _lg.error(f"requires_human agent error: {e}")
            return RequiresHumanDecision(requires_human=True, rationale=f"Agent error: {e}", missing_inputs=None)

# Structured evaluation of answer responsiveness
class AnswerResponsiveness(BaseModel):
    """Determines if an answer is fully responsive to the original request."""
    fully_responsive: bool = Field(
        ..., description="True if the answer fully addresses the original request."
    )
    revised_prompt: Optional[str] = Field(
        default=None,
        description="If not fully responsive, a paraphrased prompt that clarifies expectations, output form, and resolves ambiguity."
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Brief rationale explaining gaps or mismatches."
    )

class ReviewPrompts:
    @classmethod
    def assess_responsiveness(cls, request: str, answer: str) -> AnswerResponsiveness:
        """
        Returns whether the answer is fully responsive to the original request.
        If not, provides a revised prompt that better specifies the expected answer form and removes ambiguity.
        """
        try:
            llm = get_analysis_llm()
            if llm is None:
                # Conservative fallback
                return AnswerResponsiveness(
                    fully_responsive=False,
                    revised_prompt=f"Revise and fully answer the following request. Provide a complete, unambiguous response with clear structure and all required details.\n\nRequest: {request}",
                    rationale="LLM unavailable; cannot assess."
                )

            prompt = ChatPromptTemplate.from_messages([
                ("system",
                 "You are a strict evaluator. Determine if the provided answer fully and directly addresses the user's original request, or if it provides a plan that would, upon completion, fully answer the user's original request. "
                 "If not, draft a revised prompt that clarifies ambiguities, specifies the expected output format, and ensures completeness. "
                 "Return a JSON object matching the AnswerResponsiveness schema."),
                ("user",
                 "Original request:\n{request}\n\n"
                 "Provided answer:\n{answer}\n\n"
                 "Evaluate responsiveness. If not fully responsive, rewrite the prompt to elicit a complete, unambiguous answer "
                 "(include desired structure, key elements, and any constraints).")
            ])

            inst = invoke_structured_with_retry(
                llm=llm,
                prompt=prompt,
                model_cls=AnswerResponsiveness,
                inputs={"request": request, "answer": answer},
                max_attempts=2,
                repair_instruction="If your previous JSON did not match the AnswerResponsiveness schema, correct it and return only valid JSON."
            )
            if inst is None:
                return AnswerResponsiveness(
                    fully_responsive=False,
                    revised_prompt=f"Revise for completeness: {request}",
                    rationale="Could not parse model output."
                )
            return cast(AnswerResponsiveness, inst)
        except Exception as e:
            # Safe fallback on any error
            return AnswerResponsiveness(
                fully_responsive=False,
                revised_prompt=f"Improve this prompt to obtain a complete and unambiguous answer:\n\nRequest: {request}",
                rationale=f"Assessment error: {e}"
            )


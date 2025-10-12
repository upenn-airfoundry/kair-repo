from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder  # needed for agent prompt placeholders
from langchain.schema.output_parser import StrOutputParser
import requests

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union, Any
from enrichment.llms import get_agentic_llm

# Add the new Pydantic models for learning resources
class LearningResource(BaseModel):
    """A learning resource related to a specific topic."""
    title: str = Field(..., description="The title of the learning resource.")
    rationale: str = Field(..., description="A brief explanation of why this resource is relevant and useful.")
    url: str = Field(..., description="The URL of the learning resource.")

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


# Pydantic models for describing dependencies between tasks in a SolutionPlan
class TaskDependency(BaseModel):
    """Represents a single dependency between two tasks in a solution plan."""
    source_task_id: str = Field(..., description="The unique identifier of the source task that produces the data.")
    source_task_description: str = Field(..., description="The full 'description_and_goals' of the source task that produces the data.")
    dependent_task_id: str = Field(..., description="The unique identifier of the dependent task that consumes the data.")
    dependent_task_description: str = Field(..., description="The full 'description_and_goals' of the dependent task that consumes the data.")
    data_schema: str = Field(..., description="The schema of the data flowing from the source to the dependent task, formatted as 'field:type'.")
    data_flow_type: Literal["automatic", "gated by user feedback", "rethinking the previous task"] = Field(..., description="The nature of the data flow between the tasks.")
    relationship_description: str = Field(..., description="A description of the dependency, including the criteria evaluated from the source task's output before the dependent task can proceed.")

class TaskDependencyList(BaseModel):
    """A list of dependencies between tasks."""
    dependencies: List[TaskDependency]


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
    query_class: Literal["general_knowledge", "learning_resources_or_technical_training", "papers_reports_or_prior_work", "molecules_algorithms_solutions_strategies_or_plans"]
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
             "You have tools available, including a Semantic Scholar search tool. "
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


class PeoplePrompts:
    
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
            # TODO: if pubs is empty we need to fetch
            profile = scholar_search_gscholar_by_id(graph_accessor, scholar_id, [])

            if profile:
                return profile.get("articles", [])
        if author_data:
            return author_data.get("articles", [])
        else:
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
        structured_llm = llm.with_structured_output(PersonOfInterest)
        chain = prompt | structured_llm
        result = chain.invoke({})
        # Return as dict with required keys
        return {
            "biosketch": result.biosketch,
            "expertise": result.expertise_and_research,
            "projects": result.known_projects
        }
        
    @classmethod
    def classify_query_and_summarize(query: str) -> QueryClassification:
        # Use a fast LLM (e.g., Gemini Flash or GPT-3.5) with a structured output
        from enrichment.llms import get_analysis_llm
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Classify the following query and summarize the task. Respond with a JSON object matching the QueryClassification schema."),
            ("user", f"Query: {query}")
        ])
        llm = get_analysis_llm().with_structured_output(QueryClassification)
        result = (prompt | llm).invoke({"query": query})
        return result

class QueryPrompts:
    @classmethod
    def build_expanded_prompt(cls, system_profile: str, user_profile: dict, user_history: list, task_summary: str, user_prompt: str):
        history_str = ""
        for items in user_history[-5:]:
            prompt = items[0]
            response = items[1]
            history_str += f"User: {prompt}\nSystem: {response}\n"
        context = (
            f"General instructions: {system_profile}\n"
            f"User expertise: {user_profile.get('expertise','')}\n"
            f"Projects and interests: {user_profile.get('projects','')}\n"
            f"Task summary: {task_summary}\n"
            f"Recent history:\n{history_str}\n"
            f"Current query: {user_prompt}"
        )
        return context

    def classify_query_and_summarize(query: str) -> QueryClassification:
        # Use a fast LLM (e.g., Gemini Flash or GPT-3.5) with a structured output
        from enrichment.llms import get_analysis_llm
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Classify the following query and summarize the task. Respond with a JSON object matching the QueryClassification schema."),
            ("user", f"Query: {query}")
        ])
        llm = get_analysis_llm().with_structured_output(QueryClassification)
        result = (prompt | llm).invoke({"query": query})
        return result


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

        structured_llm = llm.with_structured_output(SolutionPlan)
        chain = prompt | structured_llm

        result = chain.invoke({"user_request": user_request})
        return result

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

        structured_llm = llm.with_structured_output(TaskDependencyList)
        chain = prompt | structured_llm

        result = chain.invoke({"solution_plan_str": plan_str})
        return result

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
                if not name:
                    continue
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
                    # FIX: await invoke
                    search_results = await mcp_client.invoke(search_tool_name, search_args)
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
                # FIX: await invoke
                analyzer_res = await mcp_client.invoke("index_papers", analyzer_args)
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
from typing import List, Optional, Literal, Union
from enrichment.llms import get_agentic_llm

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
                 "You are a strict evaluator. Determine if the provided answer fully and directly addresses the user's original request. "
                 "If not, draft a revised prompt that clarifies ambiguities, specifies the expected output format, and ensures completeness. "
                 "Return a JSON object matching the AnswerResponsiveness schema."),
                ("user",
                 "Original request:\n{request}\n\n"
                 "Provided answer:\n{answer}\n\n"
                 "Evaluate responsiveness. If not fully responsive, rewrite the prompt to elicit a complete, unambiguous answer "
                 "(include desired structure, key elements, and any constraints).")
            ])

            structured_llm = llm.with_structured_output(AnswerResponsiveness)  # type: ignore
            result: AnswerResponsiveness = (prompt | structured_llm).invoke({
                "request": request,
                "answer": answer
            })
            return result
        except Exception as e:
            # Safe fallback on any error
            return AnswerResponsiveness(
                fully_responsive=False,
                revised_prompt=f"Improve this prompt to obtain a complete and unambiguous answer:\n\nRequest: {request}",
                rationale=f"Assessment error: {e}"
            )


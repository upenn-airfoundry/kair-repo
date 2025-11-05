from dotenv import load_dotenv, find_dotenv
import os
import logging
from typing import Any, List, Optional
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

# Replace create_react_agent with create_tool_calling_agent
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.exceptions import OutputParserException

try:
    from langchain_openai.embeddings import OpenAIEmbeddings
except ImportError:
    OpenAIEmbeddings = None


_ = load_dotenv(find_dotenv())


mcp_client = MultiServerMCPClient(
    {
        "SemanticScholarSearch": {
            # Make sure you start your server on port 8000
            "url": "http://localhost:8000/mcp",
            "transport": "streamable_http",
        },
        # "PDFAnalyzer": {
        #     # Make sure you start your server on port 8001
        #     "url": "http://localhost:8001/mcp",
        #     "transport": "streamable_http",
            
        # },
        "SearchAPI": {
            # Make sure you start your server on port 8002
            "url": "http://localhost:8002/mcp",
            "transport": "streamable_http",
            
        }
    })

# Define the argument schema for the Semantic Scholar tool
# class SemanticScholarSearch(BaseModel):
#     """
#     A tool to search for papers on Semantic Scholar.
#     """
#     tool: str = Field("paper_relevance_search", description="Search for papers on Semantic Scholar.")
#     fields: List[str] = Field(
#         default_factory=lambda: ["title", "authors", "year", "abstract", "url"],
#         description="The fields to return for each paper."
#     )
#     query: str = Field(..., description="The search query for papers.")
    # limit: int = Field(5, description="The maximum number of papers to return.")

# Store tools in a dictionary for easy access
# In the future, you can load these from your config.json
# MCP_TOOLS = {
#     "SemanticScholarSearch": SemanticScholarSearch,
# }


# def call_mcp(tool_name: str, tool_args: dict) -> dict:
#     """
#     Calls a named MCP tool via HTTP POST request, handling an SSE stream.

#     Args:
#         tool_name (str): The name of the tool to call (must match a key in MCP_CONFIG).
#         tool_args (dict): The arguments to pass as a JSON payload to the tool.

#     Returns:
#         dict: A dictionary containing a 'results' key with a list of all JSON objects 
#               received from the stream, or an 'error' key on failure.
#     """

#     try:
#         logging.info(f"Calling MCP server with args: {tool_args}")

#         tools = asyncio.run(load_mcp_tools(mcp_client.session("SemanticScholarSearch"), mcp_client))
        
#         results = []
#         # Use a context manager to handle the streaming connection
#         results = mcp_client.invoke(tool_name, tool_args)
        

#         logging.info(f"Received {len(results)} items from MCP stream.")
#         # Return the collected results in a structured dictionary
#         return {"results": results}

#     except requests.exceptions.RequestException as e:
#         error_message = f"Error: Could not connect to the MCP server at {base_url}. Please ensure it is running. Details: {e}"
#         logging.error(error_message)
#         return {"error": error_message}
#     except Exception as e:
#         error_message = f"An unexpected error occurred during MCP call: {e}"
#         logging.error(error_message)
#         return {"error": error_message}


# Lazy imports to avoid crashing at import time if credentials are missing
def _import_openai_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI

def _import_vertex_llm():
    # Import ChatVertexAI; callers should be prepared to handle ImportError
    from langchain_google_vertexai import ChatVertexAI  # may raise ImportError on version mismatch
    return ChatVertexAI

def _import_genai_embeddings():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    return GoogleGenerativeAIEmbeddings

_vertex_initialized = False

def _ensure_vertex_initialized():
    global _vertex_initialized
    if not _vertex_initialized:
        try:
            from google.cloud import aiplatform
            project = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('GCP_PROJECT') or os.getenv('GOOGLE_PROJECT_ID') or os.getenv('GCP_PROJECT_ID')
            location = os.getenv('GOOGLE_CLOUD_REGION') or os.getenv('GCP_REGION') or 'us-central1'
            aiplatform.init(project=project, location=location)
        except Exception:
            pass
        _vertex_initialized = True

def _build_doc_embeddings():
    _ensure_vertex_initialized()
    return _import_genai_embeddings()(model="models/gemini-embedding-001", task_type="RETRIEVAL_DOCUMENT")

def _build_query_embeddings():
    _ensure_vertex_initialized()
    return _import_genai_embeddings()(model="models/gemini-embedding-001", task_type="RETRIEVAL_QUERY")


def qwen_doc_embedding(text):
    return [[0.0] * 4096 for _ in text] if isinstance(text, list) else [0.0] * 4096




def gemini_doc_embedding(text):
    try:
        embeddings = _build_doc_embeddings()
        if isinstance(text, list):
            return embeddings.embed_documents(text)
        else:
            return embeddings.embed_documents([text])[0]
    except Exception:
        # Fallback to a zero vector length 3072
        return [[0.0] * 3072 for _ in text] if isinstance(text, list) else [0.0] * 3072


def gemini_query_embedding(query):
    try:
        embeddings = _build_query_embeddings()
        return embeddings.embed_query(query)
    except Exception:
        return [0.0] * 1536


def get_structured_analysis_llm():
    try:
        ChatOpenAI = _import_openai_llm()
        return ChatOpenAI(model="gpt-4.1-mini", temperature=0.1)
    except Exception as e:
        print(f"Error initializing OpenAI LLM: {e}")
        return None

def _make_llm(model: str, temperature: float = 0.0, max_tokens: Optional[int] = None):
    """
    Try Vertex Chat first; if that import fails (e.g., due to a LangChain mismatch),
    fall back to Google GenAI (AI Studio) client; then to OpenAI as last resort.
    """
    # 1) Vertex AI (preferred)
    try:
        ChatVertexAI = _import_vertex_llm()
        _ensure_vertex_initialized()
        return ChatVertexAI(model=model, temperature=temperature, max_tokens=max_tokens, max_retries=6, stop=None)
    except Exception as e:
        logging.warning(f"Vertex Chat import/init failed, falling back to Google GenAI: {e}")
    # 2) Google GenAI (langchain-google-genai)
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        # ChatGoogleGenerativeAI uses max_output_tokens instead of max_tokens
        kwargs = dict(model=model, temperature=temperature)
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        return ChatGoogleGenerativeAI(**kwargs)
    except Exception as e:
        logging.warning(f"Google GenAI init failed, falling back to OpenAI: {e}")
    # 3) OpenAI fallback
    try:
        ChatOpenAI = _import_openai_llm()
        return ChatOpenAI(model=os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"), temperature=temperature)
    except Exception as e:
        logging.error(f"OpenAI fallback init failed: {e}")
        return None

def get_analysis_llm():
    # Light, fast model for structured analysis
    return _make_llm("gemini-2.0-flash-lite-001", temperature=0, max_tokens=None)

def get_better_llm():  # use_mcp_tools: bool = False
     """
     Returns a high-quality Gemini model instance.

     Args:
         use_mcp_tools (bool): If True, binds the available MCP tools to the LLM.

     Returns:
         ChatVertexAI: An instance of the Gemini model.
     """
     return _make_llm("gemini-2.5-flash", temperature=0, max_tokens=None)


def _patch_pydantic_schema_v1(schema: dict):
    """
    Patches a Pydantic v2 schema to be compatible with older parsers
    by copying '$defs' to 'definitions' if it exists.
    """
    if '$defs' in schema:
        schema['definitions'] = schema['$defs']

def _patch_google_schema(schema_node: Any):
    """
    Recursively traverses a JSON schema and applies patches for Google compatibility:
    1. Converts 'type' values to uppercase (e.g., 'string' -> 'STRING').
    2. Removes '{"type": "null"}' from 'anyOf' arrays for optional fields and simplifies the structure.
    """
    if isinstance(schema_node, dict):
        # Handle 'anyOf' for optional fields (e.g., Union[str, None])
        if 'anyOf' in schema_node and isinstance(schema_node['anyOf'], list):
            # Filter out the 'type: null' part
            schema_node['anyOf'] = [item for item in schema_node['anyOf'] if item.get('type') != 'null']
            # If only one type remains (the common case for Optional[T]),
            # hoist the single remaining item up and remove the 'anyOf'.
            if len(schema_node['anyOf']) == 1:
                single_item = schema_node.pop('anyOf')[0]
                schema_node.update(single_item)

        # Use list(schema_node.items()) to allow modification during iteration
        for key, value in list(schema_node.items()):
            if key == 'type' and isinstance(value, str):
                schema_node[key] = value.upper()
            else:
                # Recurse into nested values
                _patch_google_schema(value)

    elif isinstance(schema_node, list):
        for item in schema_node:
            _patch_google_schema(item)


def _handle_agent_parsing_error(error: OutputParserException) -> str:
    return (
        "Output was not valid. Try again. "
        "If returning a final answer, return valid JSON that matches the requested schema. "
        f"Parser error: {error}"
    )

async def get_agentic_llm(prompt: ChatPromptTemplate | None = None):
    """
    Returns a Gemini-based Tool Calling agent executor with MCP tools.
    """
    tools = await mcp_client.get_tools()

    # Patch tool schemas (keep your existing patchers)
    for t in tools:
        if hasattr(t, 'args_schema') and isinstance(t.args_schema, dict):
            _patch_pydantic_schema_v1(t.args_schema)
            _patch_google_schema(t.args_schema)

    try:
        ChatVertexAI = _import_vertex_llm()
        _ensure_vertex_initialized()

        # Slightly >0 temperature to avoid degenerate empty outputs
        llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.2, max_tokens=None, max_retries=6, stop=None)

        # Default prompt for tool-calling agent (system + placeholders)
        if prompt is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant. Use tools when helpful. Think step-by-step. "
                    "If the user requests JSON, return strictly valid JSON."),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ])

        # Create a tool-calling agent (no ReAct “Action:” strings needed)
        agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=_handle_agent_parsing_error,
            max_iterations=8,
        )
        return agent_executor
    except Exception as e:
        print(f"Error initializing agentic LLM: {e}")
        return None


async def get_structured_agentic_llm(structured_model: type[BaseModel], prompt: ChatPromptTemplate | None = None):
    """
    Returns a Gemini-based Tool Calling agent executor with MCP tools.
    Note: Do NOT wrap the LLM with .with_structured_output here, because the agent
    requires a model that implements .bind_tools. Structure the final output upstream.
    """
    tools = await mcp_client.get_tools()

    # Patch tool schemas (keep your existing patchers)
    for t in tools:
        if hasattr(t, 'args_schema') and isinstance(t.args_schema, dict):
            _patch_pydantic_schema_v1(t.args_schema)
            _patch_google_schema(t.args_schema)

    try:
        ChatVertexAI = _import_vertex_llm()
        _ensure_vertex_initialized()

        # Slightly >0 temperature to avoid degenerate empty outputs
        llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.2, max_tokens=None, max_retries=6, stop=None)

        # Default prompt for tool-calling agent (system + placeholders)
        if prompt is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant. Use tools when helpful. Think step-by-step. "
                    "If the user requests JSON, return strictly valid JSON."),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ])

        # Create a tool-calling agent (no ReAct “Action:” strings needed)
        agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=_handle_agent_parsing_error,
            max_iterations=8,
        )
    except Exception as e:
        print(f"Error initializing agentic LLM: {e}")
        return None


# def call_llm_with_tools(user_prompt: str):
#     """
#     Example function demonstrating how to call the LLM with tools and handle the response.
#     """
#     print(f"User Prompt: {user_prompt}")
#     llm = get_better_llm(use_mcp_tools=True)
#     if not llm:
#         return "LLM not available."

#     # First invocation to get the tool call from the LLM
#     ai_msg = llm.invoke(user_prompt)

#     if not ai_msg.tool_calls:
#         print("LLM responded directly without calling a tool.")
#         return ai_msg.content

#     # Handle the tool call
#     tool_results = []
#     for tool_call in ai_msg.tool_calls:
#         tool_name = tool_call['name']
#         print(f"LLM wants to call tool: {tool_name} with args: {tool_call['args']}")

#         # Use the new helper function to call the tool
#         tool_output = call_mcp(tool_name, tool_call['args'])

#         tool_results.append({
#             "tool_call_id": tool_call['id'],
#             "output": json.dumps(tool_output) # Convert the final list of results to a string for the LLM
#         })

#     # Second invocation: provide the tool results back to the LLM
#     print(f"Providing tool results back to LLM: {tool_results}")
#     final_response = llm.with_config(
#         {"run_name": "invoke_with_tool_results"}
#     ).invoke(
#         [ai_msg] + [("tool", str(res), res["tool_call_id"]) for res in tool_results]
#     )

#     return final_response.content

def generate_openai_embedding(content: str) -> List[float]:
    """Generate an embedding for the given content using LangChain and OpenAI."""
    try:
        if OpenAIEmbeddings is None:
            logging.error("OpenAIEmbeddings not available, using fallback")
            return [0.0] * 1536  # Return a zero vector as a fallback
        # Initialize OpenAI embeddings
        embeddings = OpenAIEmbeddings()
        #embeddings = get_embedding()
        # Generate the embedding for the content
        embedding = embeddings.embed_query(content)
        return embedding
    except Exception as e:
        logging.error(f"Error generating embedding: {e}")
        return [0.0] * 1536  # Return a zero vector as a fallback

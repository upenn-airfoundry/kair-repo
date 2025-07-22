from langchain_openai import ChatOpenAI
from langchain_google_vertexai import ChatVertexAI
from google.cloud import aiplatform
import google.generativeai as genai

#from langchain_google_vertexai import GoogleGenerativeAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from dotenv import load_dotenv, find_dotenv
import os

_ = load_dotenv(find_dotenv())

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.expanduser("~/.config/gcloud/air-foundry-seas-8645-7ff9e2da3f97.json")#application_default_credentials.json")

# Initialize the a specific Embeddings Model version
doc_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    task_type="RETRIEVAL_DOCUMENT")

# Initialize the a specific Embeddings Model version
query_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    task_type="RETRIEVAL_QUERY")

# Initialize Vertex AI
aiplatform.init(project='air-foundry-seas-8645', location='us-east1')  # e.g., "us-central1"

#better_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.1)

structured_analysis_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.1)

analysis_llm = ChatVertexAI(
    model="gemini-2.0-flash-lite-001",
    temperature=0,
    max_tokens=None,
    max_retries=6,
    stop=None,
    # other params...
)

better_llm = ChatVertexAI(
    model="gemini-2.0-flash-001",
    temperature=0,
    max_tokens=None,
    max_retries=6,
    stop=None,
    # other params...
)

# Use Gemini embeddings
def gemini_doc_embedding(text):
    # result = genai.embed_content(
    #     model="models/embedding-001",
    #     content=text,
    #     task_type="retrieval_document"
    # )
    # return result['embedding']
    if isinstance(text, list):
        return doc_embeddings.embed_documents(text)
    else:
        return doc_embeddings.embed_documents([text])[0]

# Use Gemini embeddings
def gemini_query_embedding(query):
    return query_embeddings.embed_query(query)

from dotenv import load_dotenv, find_dotenv
import os
import logging

_ = load_dotenv(find_dotenv())




# Lazy imports to avoid crashing at import time if credentials are missing
def _import_openai_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI

def _import_vertex_llm():
    from langchain_google_vertexai import ChatVertexAI
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


def gemini_doc_embedding(text):
    try:
        embeddings = _build_doc_embeddings()
        if isinstance(text, list):
            return embeddings.embed_documents(text)
        else:
            return embeddings.embed_documents([text])[0]
    except Exception:
        # Fallback to a zero vector length 1536
        return [[0.0] * 1536 for _ in text] if isinstance(text, list) else [0.0] * 1536


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

def get_analysis_llm():
    try:
        ChatVertexAI = _import_vertex_llm()
        _ensure_vertex_initialized()
        return ChatVertexAI(model="gemini-2.0-flash-lite-001", temperature=0, max_tokens=None, max_retries=6, stop=None)
    except Exception as e:
        print(f"Error initializing Vertex AI LLM: {e}")
        return None

def get_better_llm():
    try:
        ChatVertexAI = _import_vertex_llm()
        _ensure_vertex_initialized()
        return ChatVertexAI(model="gemini-2.0-flash-001", temperature=0, max_tokens=None, max_retries=6, stop=None)
    except Exception as e:
        print(f"Error initializing Vertex AI LLM: {e}")
        return None

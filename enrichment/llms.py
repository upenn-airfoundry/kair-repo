from langchain_openai import ChatOpenAI
from langchain_google_vertexai import ChatVertexAI
from google.cloud import aiplatform

from dotenv import load_dotenv, find_dotenv
import os

_ = load_dotenv(find_dotenv())

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")

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
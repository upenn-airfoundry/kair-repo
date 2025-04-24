from langchain_openai import ChatOpenAI
from dotenv import load_dotenv, find_dotenv
import os

_ = load_dotenv(find_dotenv())

analysis_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1, api_key=os.getenv("OPENAI_API-KEY")) # gpt-4o-preview is the correct model name.


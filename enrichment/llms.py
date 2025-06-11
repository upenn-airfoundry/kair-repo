from langchain_openai import ChatOpenAI
from dotenv import load_dotenv, find_dotenv
import os

_ = load_dotenv(find_dotenv())

better_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.1)

analysis_llm = ChatOpenAI(model="gpt-4.1-nano", temperature=0.1)


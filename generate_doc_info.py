import traceback
import os
import json

from datetime import datetime
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

graph_db = GraphAccessor()

def parse_pdfs_and_index():
    # Fetch all papers
    papers = graph_db.exec_sql("SELECT id, path FROM crawled;")

    for paper_id, path in papers:
        # Parse the PDF using Langchain PDF parser
        pdf_path = os.path.join(DOWNLOAD_DIR, path)
        
        print(f"Parsing PDF: {path}")
        
        # Get today's date
        the_date = datetime.now().date()
        
        try:
            loader = PyPDFLoader(pdf_path)
            documents = loader.load()
            
            # Use the most common splitter: RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            split_docs = splitter.split_documents(documents)

            # Take the first 4 splits and concatenate them
            concatenated_text = " ".join(doc.page_content for doc in split_docs[:2])

            # Use GPT-4o-mini to extract summary and authors
            llm = ChatOpenAI(model="gpt-4o-mini")  # Use ChatOpenAI for chat models
            prompt_template = ChatPromptTemplate.from_template(
                """Extract the title, research field, summary and authors from the following text. 
                If available, include authors' email addresses and affiliations in JSON format. 
                Text:
                {text}

                Output format:
                {{
                "title": "...",
                "field": "...",
                "summary": "...",
                "authors": [
                    {{"name": "...", "email": "...", "affiliation": "..."}},
                    ...
                ]
                }}
                """
            )

            prompt = prompt_template.format_messages(text=concatenated_text)

            response = llm.invoke(prompt)
            response_text = response.content
            
            if '```' in response_text:
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text.split('json')[1]
                response_text = response_text.strip()
            
            paper_id = 0
            try:
                extracted_info = json.loads(response_text)

                # Print the extracted JSON
                # print(f"Extracted Info: {json.dumps(extracted_info, indent=2)}")
                
                                # Add the paper to the database
                title = extracted_info.get("title", "Unknown Title")
                field = extracted_info.get("field", "Unknown Field")
                summary = extracted_info.get("summary", "No Summary Available")
                paper_id = graph_db.add_paper(url=path, crawl_time=str(the_date), title=title, summary=summary)
                
                print ("Added paper " + str(paper_id) + " with title " + title)
                
                graph_db.add_tag_to_paper(paper_id, "field", field)
                
                print ("Added summary " + summary)

                # Add authors to the database
                authors = extracted_info.get("authors", [])
                for author in authors:
                    name = author.get("name", "Unknown Author")
                    email = author.get("email", None)
                    affiliation = author.get("affiliation", None)
                    author_id = graph_db.add_author(name=name, email=email, organization=affiliation)
                    graph_db.link_author_to_paper(author_id, paper_id)
                    print(f"Added author: {name} (ID: {author_id})")

            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                print("Raw response text:")
                print(response_text)
            
            # Index the paragraphs
            for doc in split_docs:
                content = doc.page_content
                print(f"Indexing paragraph: {content}")
                (para_id, embedding) = graph_db.add_paragraph(paper_id, content)
            graph_db.commit()

        except Exception as e:
            print(f"Error processing PDF {pdf_path}: {e}")
            traceback.print_exc()
            

if __name__ == "__main__":
    parse_pdfs_and_index()
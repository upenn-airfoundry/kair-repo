from flask import Flask, jsonify
from graph_db import GraphAccessor
from flask import request
from crawler import fetch_and_crawl
from datetime import datetime
from flask_cors import CORS

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain

app = Flask("KAIR")
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173"], \
    "methods": ["GET", "POST", "PUT", "DELETE"],
    "allow_headers": ["Content-Type", "Authorization"],
    "expose_headers": ["X-Custom-Header"],
    "supports_credentials": True}})  # Enable CORS for all routes

# Initialize the GraphAccessor
graph_accessor = GraphAccessor()

@app.route('/find_related_entities_by_tag', methods=['GET'])
def find_related_entities_by_tag():
    """
    Endpoint to find entities whose tag (with a specified tag_name) has a tag_value
    whose embedding approximately matches the query embedding.
    """
    tag_name = request.args.get('tag_name')
    query = request.args.get('query')
    k = int(request.args.get('k', 10))  # Default to 10 if not provided

    if not tag_name or not query:
        return jsonify({"error": "Both 'tag_name' and 'query' parameters are required"}), 400

    query_embedding = graph_accessor._generate_embedding(query)
    results = graph_accessor.find_entities_by_tag_embedding(query_embedding, tag_name, k)

    return jsonify({"results": results})

@app.route('/find_related_entities', methods=['GET'])
def find_related_entities():
    """
    Endpoint to find entities related to a particular concept by matching against
    the entity_embed field using vector distance.
    """
    query = request.args.get('query')
    k = int(request.args.get('k', 10))  # Default to 10 if not provided
    entity_type = request.args.get('entity_type')  # Optional
    keywords = request.args.getlist('keywords')  # Optional list of keywords

    if not query:
        return jsonify({"error": "'query' parameter is required"}), 400

    concept_embedding = graph_accessor._generate_embedding(query)
    results = graph_accessor.find_related_entities_by_embedding(concept_embedding, k, entity_type, keywords)

    return jsonify({"results": results})


@app.route('/add_to_crawl_queue', methods=['POST'])
def add_to_crawl_queue():
    """
    Endpoint to add a URL into the crawl queue.
    """
    url = request.json.get('url')
    comment = request.json.get('comment', None)  # Optional comment

    if not url:
        return jsonify({"error": "'url' parameter is required"}), 400

    # Check if the URL already exists in the crawl_queue table
    exists = graph_accessor.exec_sql("SELECT 1 FROM crawl_queue WHERE url = %s;", (url,))
    if len(exists) > 0:
        return jsonify({"message": "URL already exists in the crawl queue"}), 200

    # Insert the URL into the crawl_queue table
    graph_accessor.execute(
        "INSERT INTO crawl_queue (create_time, url, comment) VALUES (%s, %s, %s);",
        (datetime.now().date(), url, comment)
    )
    graph_accessor.commit()

    return jsonify({"message": "URL added to crawl queue"}), 201


@app.route('/crawl_pdf', methods=['POST'])
def crawl_pdf():
    """
    Endpoint to crawl PDFs from the crawl queue.
    """
    try:
        fetch_and_crawl()
        return jsonify({"message": "Crawling completed successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred during crawling: {e}"}), 500


@app.route('/parse_pdfs_and_index', methods=['POST'])
def parse_pdfs_and_index_endpoint():
    """
    Endpoint to parse PDFs and index them into the database.
    """
    try:
        parse_pdfs_and_index(use_aryn=False)
        return jsonify({"message": "PDF parsing and indexing completed successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred during parsing and indexing: {e}"}), 500


@app.route('/uncrawled_entries', methods=['GET'])
def get_uncrawled_entries():
    """
    Endpoint to show entries in the crawl_queue that have not yet been crawled.
    """
    try:
        query = """
            SELECT cq.id, cq.create_time, cq.url, cq.comment
            FROM crawl_queue cq
            LEFT JOIN crawled c ON cq.id = c.id
            WHERE c.id IS NULL;
        """
        uncrawled_entries = graph_accessor.exec_sql(query)
        results = [
            {"id": row[0], "create_time": row[1], "url": row[2], "comment": row[3]}
            for row in uncrawled_entries
        ]
        return jsonify({"uncrawled_entries": results}), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred while fetching uncrawled entries: {e}"}), 500

@app.route('/expand', methods=['POST'])
def expand_search():
    """
    Endpoint to process a user question or prompt using LangChain and GPT-4o-mini
    with chain-of-thought reasoning.
    """
    try:
        # Get the user question or prompt from the request
        user_prompt = request.json.get('prompt')
        if not user_prompt:
            print ("'prompt' parameter is missing")
            return jsonify({"error": "'prompt' parameter is required"}), 400

        # Initialize the GPT-4o-mini model
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        # Define the chain-of-thought reasoning prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that uses chain-of-thought reasoning to answer questions."),
            ("user", "{question}"),
            ("assistant", "Let's think about what questions we need to ask.")
        ])

        chain = prompt | llm

        # Run the chain with the user prompt
        response = chain.invoke({"question": user_prompt})
        
        print(response.text)

        # Return the response in JSON format
        return jsonify({"data": {"message": response.content} }), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500


if __name__ == '__main__':
    app.run(port=8081,debug=True) 
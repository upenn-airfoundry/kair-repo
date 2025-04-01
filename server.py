from flask import Flask, jsonify
from graph_db import GraphAccessor
from flask import request
from crawler import fetch_and_crawl
from datetime import datetime
from flask_cors import CORS
import json

from generate_detection_info import get_papers_by_field, get_entities_from_db
from generate_detection_info import answer_from_summary

from search import search_over_criteria, search_multiple_criteria
from search import generate_rag_answer

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

    query_embedding = graph_accessor.generate_embedding(query)
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
    keywords = request.args.get('keywords').split(',')  # Optional list of keywords
    
    if keywords[0] == '':
        keywords = None
    
    print( request.args)

    if not query:
        return jsonify({"error": "'query' parameter is required"}), 400

    print ("Find related entities: ", query)
    results = graph_accessor.find_related_entities(query, k, entity_type, keywords)

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
    
@app.route('/get_assessment_criteria', methods=['GET'])
def get_assessment_criteria():
    """
    Endpoint to get the assessment criteria for papers.
    """
    try:
        name = request.args.get('name')
        criteria = graph_accessor.get_assessment_criteria(name)
        if criteria:
            return jsonify({"criteria": criteria}), 200
        else:
            if name:
                return jsonify({"error": "No criteria found for the given name"}), 404
            else:
                return jsonify({"error": "Please create some assessment criteria"}), 404
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/add_assessment_criterion', methods=['POST'])
def add_assessment_criterion():
    """
    Endpoint to add an assessment criterion to the database.
    """
    try:
        # Parse the request JSON
        data = request.json
        name = data.get('name')
        scope = data.get('scope')
        prompt = data.get('prompt')
        promise = data.get('promise', 1.0)  # Default promise value is 1.0

        # Validate required fields
        if not name or not prompt or not scope:
            return jsonify({"error": "'name', 'scope', and 'prompt' fields are required"}), 400
        
        print("Adding assessment criterion with name:", name)
        print("Scope:", scope)
        print("Prompt:", prompt)

        # Call the GraphAccessor method to add the assessment criterion
        criterion_id = graph_accessor.add_assessment_criterion(name, prompt, scope, promise)

        # Return the newly created criterion ID
        return jsonify({"message": "Assessment criterion added successfully", "criterion_id": criterion_id}), 201

    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/add_enrichment', methods=['POST'])
def add_enrichment():
    criteria = graph_accessor.get_assessment_criteria(None)
    
    for criterion in criteria:
        name = criterion['name']
        scope = criterion['scope']
        prompt = criterion['prompt']
        # promise = criterion['promise']
        
        relevant_papers = get_papers_by_field(scope, 30)
        
        for paper in relevant_papers:
            result = get_entities_from_db(paper[0])
            if result is None:
                continue

            for row in result:
                data = row['json']
                
                # print(data)
                result = answer_from_summary(json.loads(data), prompt)
                
                if result is None or result == 'none':
                    continue
                
                print (result)
                graph_accessor.add_tag_to_paper(paper[0], name, result)
        
    return jsonify({"message": "Enrichment step completed"}), 201


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

        """
        1. What characteristics should we look for in the authors and sources?
        2. What field should we focus on for papers?
        3. How many citations did the paper receive?
        4. What are the main topics covered in the paper?
        5. What are the main findings or conclusions of the paper?
        6. What are the implications of the findings?
        7. What are the limitations of the study?
        8. What future research directions are suggested?
        9. What are the main contributions of the paper?
        10. What are the key methodologies used in the paper?
        11. What are the main theories or frameworks discussed?
        12. What are the main arguments or claims made by the authors?
        13. What are the main research questions addressed?
        14. What are the main hypotheses tested?
        15. What are the main variables or constructs studied?
        16. What are the main data sources used?
        17. What are the main analytical techniques used?
        18. What are the main results or findings?
        19. What are the main conclusions drawn?
        20. What are the main recommendations made?
        21. What are the main implications for practice or policy?
        22. What are the main implications for theory or research?
        23. What are the main implications for future research?
        """

        questions = search_over_criteria(user_prompt, graph_accessor.get_assessment_criteria());
        
        print('Expanded into subquestions: ' + questions)
        
        relevant_docs = search_multiple_criteria(questions)
        
        # TODO: from paragraph to paper
        #main = graph_accessor.find_related_entity_ids(user_prompt, 100)
        main = graph_accessor.find_related_entity_ids_by_tag(user_prompt, "summary", 50)
        print ("Relevant docs: " + str(relevant_docs))
        
        print ("Main papers: " + str(main))
        
        docs_in_order = []
        
        count = 0
        for doc in relevant_docs:
            if doc in set(main):
                docs_in_order.append(doc)
                count += 1
                if count >= 10:
                    break
            
        other_docs = 0    
        while count < 10 and other_docs < len(main):
            if main[other_docs] not in set(relevant_docs):
                docs_in_order.append(main[other_docs])
                count += 1
            other_docs += 1
        
        print("Items matching criteria: " + str(docs_in_order))
        
        if len(docs_in_order):
            paper_info = graph_accessor.get_entities_with_summaries(list(docs_in_order))
                
            answer = generate_rag_answer(paper_info, user_prompt)

            # Return the response in JSON format
            return jsonify({"data": {"message": answer + '\n\nWe additionally looked for assessment criteria: ' + questions} }), 200
        else:
            return jsonify({"error": "No relevant papers found"}), 404
    except Exception as e:
        print(f"Error during expansion: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500


if __name__ == '__main__':
    app.run(port=8081,debug=True) 
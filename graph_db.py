############
## Basic database "graph" interface wrapper, currently
## using TimescaleDB because of scalable pgvectorscale
## implementation and hybrid relational/graph capabilities.
##
## Copyright (C) Zachary G. Ives, 2025
##################

import psycopg2
import os
from typing import List, Tuple, Optional

from langchain_openai.embeddings import OpenAIEmbeddings

from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
_ = load_dotenv(find_dotenv())

class GraphAccessor:
    def __init__(self):
        self.conn = psycopg2.connect(dbname=os.getenv("DB_NAME"), \
                            user=os.getenv("DB_USER"), \
                            password=os.getenv("DB_PASSWORD"), \
                            host=os.getenv("DB_HOST", "localhost"), \
                            port=os.getenv("DB_PORT", "5432") \
        )
        
    def exec_sql(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        """Execute an SQL query and return the results."""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
        
    def execute(self, sql: str, params: Tuple = ()):
        """Execute an SQL query and return the results."""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            
    def commit(self):
        """Commit the current transaction."""
        self.conn.commit()
        
    def paper_exists(self, url: str) -> bool:
        """Check if a paper exists in the database by URL."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entities WHERE entity_type = 'paper' AND entity_url = %s;", (url, ))
            result = cur.fetchone()
            return result is not None
        
    def add_paper(self, url: str, crawl_time: str, title: str, summary: str) -> int:
        """Store a paper by URL and return its paper ID."""
        with self.conn.cursor() as cur:
            # See if paper already exists
            cur.execute("SELECT entity_id FROM entities WHERE entity_type = 'paper' AND entity_url = %s;", (url, ))
            paper_id = cur.fetchone()
            if paper_id is not None:
                paper_id = paper_id[0]
                
                cur.execute("SELECT tag_value FROM entity_tags WHERE entity_id = %s AND tag_name = %s;", (paper_id, "summary"))
                the_tag = cur.fetchone()
                if the_tag is None:
                    cur.execute ("INSERT INTO entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self._generate_embedding(summary)))
            else:            
                cur.execute("INSERT INTO entities (entity_url, entity_type, entity_name) VALUES (%s, %s, %s) RETURNING entity_id;", (url,'paper',title))
                paper_id = cur.fetchone()[0]
            
                cur.execute ("INSERT INTO entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self._generate_embedding(summary)))
        self.conn.commit()
        return paper_id
    
    def update_paper(self, paper_id: int, url: Optional[str] = None, crawl_time: Optional[str] = None):
        """Update all fields of a paper given its ID."""
        with self.conn.cursor() as cur:
            if url is not None:
                cur.execute("UPDATE entities SET url = %s WHERE entity_id = %s;", (url, paper_id))
            if crawl_time is not None:
                cur.execute("UPDATE entities SET crawl_time = %s WHERE entity_id = %s;", (crawl_time, paper_id))
        self.conn.commit()

    def fetch_paper_paragraphs(self, paper_id: int) -> List[str]:
        """Fetch a paper's paragraphs by paper ID."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT entity_detail FROM entities WHERE entity_type = 'paragraph' and entity_parent = %s;", (paper_id,))
            paragraphs = [row[0] for row in cur.fetchall()]
        return paragraphs

    def add_source(self, url: str) -> int:
        """Add a source by URL and return its source ID."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO entities (entity_type, entity_url) VALUES (%s,%s) RETURNING entity_id;", ('source', url,))
            source_id = cur.fetchone()[0]
        self.conn.commit()
        return source_id

    def link_source_to_paper(self, source_id: int, paper_id: int):
        """Link a source ID to a paper ID."""
        with self.conn.cursor() as cur:
            # Check if the link already exists
            cur.execute("SELECT 1 FROM entity_link WHERE from_id = %s AND to_id = %s;", (source_id, paper_id))
            the_link = cur.fetchone()
            if the_link is None:
                cur.execute("INSERT INTO entity_link (from_id, to_id, entity_strength, link_type) VALUES (%s, %s, 'source');", (source_id, paper_id,1))
        self.conn.commit()

    def link_author_to_paper(self, author_id: int, paper_id: int):
        """Link an author ID to a paper ID."""
        with self.conn.cursor() as cur:
            # Check if the link already exists
            cur.execute("SELECT 1 FROM entity_link WHERE from_id = %s AND to_id = %s;", (author_id, paper_id))
            the_link = cur.fetchone()
            if the_link is None:
                cur.execute("INSERT INTO entity_link (from_id, to_id, entity_strength, link_type) VALUES (%s, %s, %s, 'author');", (author_id, paper_id, 1))
        self.conn.commit()

    def add_paragraph(self, paper_id: int, content: str) -> Tuple[List[float], int]:
        """Add a paragraph, returning an embedding and paragraph ID."""
        embedding = self._generate_embedding(content)
        with self.conn.cursor() as cur:
            # Check if the paragraph already exists
            content = content.replace("\x00", "\uFFFD")
            cur.execute("SELECT entity_id FROM entities WHERE entity_parent = %s AND entity_type = 'paragraph' AND entity_detail = %s;", (paper_id, content,))
            paragraph_id = cur.fetchone()
            if paragraph_id is None:
                cur.execute(
                    "INSERT INTO entities (entity_parent, entity_type, entity_detail, entity_embed) VALUES (%s, 'paragraph', %s, %s) RETURNING entity_id;",
                    (paper_id, content, embedding)
                )
                paragraph_id = cur.fetchone()[0]
        self.conn.commit()
        return embedding, paragraph_id
    
    def add_author(self, name: str, email: str, organization: str) -> int:
        """Add an author by name and return their author ID."""
        with self.conn.cursor() as cur:
            # Check if the author already exists
            cur.execute("SELECT entity_id FROM entities WHERE entity_type = 'author' and entity_name = %s;", (name,))
            author_id = cur.fetchone()
            if author_id is None:
                # Add the author if they don't exist
                cur.execute("INSERT INTO entities (entity_type, entity_name) VALUES (%s, %s) RETURNING entity_id;", ('author', name,))
                author_id = cur.fetchone()[0]
            if email is not None:
                cur.execute("UPDATE entities SET entity_contact = %s WHERE entity_id = %s;", (email, author_id))
            if organization is not None:
                cur.execute("UPDATE entities SET entity_detail = %s WHERE entity_id = %s;", (organization, author_id))
        self.conn.commit()
        return author_id

    def update_paragraph(self, paragraph_id: int, content: Optional[str] = None, embedding: Optional[List[float]] = None):
        """Update all fields of a paragraph given its ID."""
        with self.conn.cursor() as cur:
            if content is not None:
                cur.execute("UPDATE entities SET entity_detail = %s WHERE entity_id = %s;", (content, paragraph_id))
            if embedding is not None:
                cur.execute("UPDATE entities SET entity_embed = %s WHERE entity_id = %s;", (embedding, paragraph_id))
        self.conn.commit()
            
    def add_tag_to_paragraph(self, paragraph_id: int, tag: str, tag_value: str):
        """Add a tag to a paragraph."""
        with self.conn.cursor() as cur:
            # Check if the tag already exists
            cur.execute("SELECT tag_value FROM paragraph_tags WHERE paragraph_id = %s AND tag_name = %s;", (paragraph_id, tag))
            the_tag = cur.fetchone()
            if the_tag is None:
                cur.execute("INSERT INTO paragraph_tags (paragraph_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paragraph_id, tag, tag_value))
            else:
                # Update the tag if it already exists
                cur.execute("UPDATE paragraph_tags SET tag_value = %s WHERE paragraph_id = %s AND tag_name = %s;", (tag_value, paragraph_id, tag))
        self.conn.commit()

    def add_tag_to_paper(self, paper_id: int, tag: str, tag_value: str):
        """Add a tag to a paper."""
        with self.conn.cursor() as cur:
            # Check if the tag already exists
            cur.execute("SELECT tag_value FROM entity_tags WHERE entity_id = %s AND tag_name = %s;", (paper_id, tag))
            the_tag = cur.fetchone()
            if the_tag is None:
                cur.execute("INSERT INTO entity_tags (entity_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paper_id, tag, tag_value))
            else:
                # Update the tag if it already exists
                cur.execute("UPDATE entity_tags SET tag_value = %s WHERE entity_id = %s AND tag_name = %s;", (tag_value, paper_id, tag))
        self.conn.commit()

    def find_paragraphs_by_tag(self, tag: str) -> List[int]:
        """Find all paragraph matches to a tag."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_tags WHERE tag_name = %s AND entity_type = 'paragraph';", (tag,))
            paragraph_ids = [row[0] for row in cur.fetchall()]
        return paragraph_ids

    def find_tags_for_paragraph(self, paragraph_id: int) -> List[str]:
        """Find all tags for a paragraph."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT tag_name FROM entity_tags WHERE entity_id = %s;", (paragraph_id,))
            tags = [row[0] for row in cur.fetchall()]
        return tags

    def find_k_most_similar_entities(self, entity_id: int, k: int) -> List[int]:
        """Find the k most similar entities given an entity."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT entity_embed FROM entities WHERE entity_id = %s;", (entity_id,))
            embedding = cur.fetchone()[0]
            cur.execute(
                """
                SELECT id FROM entities
                WHERE entity_id != %s
                ORDER BY (entity_embed <-> %s::vector) ASC
                LIMIT %s;
                """,
                (entity_id, str(embedding), k)
            )
            similar_paragraph_ids = [row[0] for row in cur.fetchall()]
        return similar_paragraph_ids

    def _generate_embedding(self, content: str) -> List[float]:
        """Generate an embedding for the given content using LangChain and OpenAI."""
        try:
            # Initialize OpenAI embeddings
            embeddings = OpenAIEmbeddings()
            # Generate the embedding for the content
            embedding = embeddings.embed_query(content)
            return embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return [0.0] * 1536  # Return a zero vector as a fallback
        
    def add_to_crawl_queue(self, url: str):
        """Add a paper URL to the crawl queue."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO crawl_queue (url) VALUES (%s);", (url,))
        self.conn.commit()

    def fetch_next_from_crawl_queue(self) -> Optional[str]:
        """Fetch the next URL from the crawl queue."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT url FROM crawl_queue ORDER BY id ASC LIMIT 1;")
            result = cur.fetchone()
            if result:
                cur.execute("DELETE FROM crawl_queue WHERE url = %s;", (result[0],))
                self.conn.commit()
                return result[0]
        return None

    def find_related_entities(self, question: str, k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[int]:
        """
        Find entities related to a particular task by matching against the entity_embed field using vector distance.
        Optionally filter by entity type and keywords.

        Args:
            question (str): The question or task to match against.
            k (int): The number of closest matches to return.
            entity_type (Optional[str]): The type of entities to filter by (e.g., 'paper', 'author').
            keywords (Optional[List[str]]): A list of keywords to match using tsvector.

        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        concept_embedding = self._generate_embedding(question)
        return self.find_related_entities_by_embedding(concept_embedding, k, entity_type, keywords)

    def find_related_entities_by_tag(self, tag_name: str, k: int = 10) -> List[int]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.
        Args:
            tag_name (str): The name of the tag to filter by.
            k (int): The number of closest matches to return.
        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query_embedding = self._generate_embedding(tag_name)
        return self.find_entities_by_tag_embedding(query_embedding, tag_name, k)

    def find_related_entities_by_embedding(self, concept_embedding: List[float], k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[int]:
        """
        Find entities related to a particular concept by matching against the entity_embed field using vector distance.
        Optionally filter by entity type and keywords.

        Args:
            concept_embedding (List[float]): The embedding of the concept to match against.
            k (int): The number of closest matches to return.
            entity_type (Optional[str]): The type of entities to filter by (e.g., 'paper', 'author').
            keywords (Optional[List[str]]): A list of keywords to match using tsvector.

        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query = """
            SELECT entity_id
            FROM entities
            WHERE (entity_embed <-> %s::vector) IS NOT NULL
        """
        params = [str(concept_embedding)]

        if entity_type:
            query += " AND entity_type = %s"
            params.append(entity_type)

        if keywords:
            query += " AND to_tsvector('english', entity_detail) @@ to_tsquery(%s)"
            ts_query = ' & '.join(keywords)
            params.append(ts_query)

        query += " ORDER BY (entity_embed <-> %s::vector) ASC LIMIT %s;"
        params.extend([str(concept_embedding), k])

        with self.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            related_entity_ids = [row[0] for row in cur.fetchall()]

        return related_entity_ids

    def find_entities_by_tag_embedding(self, query_embedding: List[float], tag_name: str, k: int = 10) -> List[int]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.

        Args:
            query_embedding (List[float]): The embedding of the query to match against.
            tag_name (str): The name of the tag to filter by.
            k (int): The number of closest matches to return.

        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query = """
            SELECT entity_id
            FROM entity_tags
            WHERE tag_name = %s
            ORDER BY (tag_embed <-> %s::vector) ASC
            LIMIT %s;
        """
        params = (tag_name, str(query_embedding), k)

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            matching_entity_ids = [row[0] for row in cur.fetchall()]

        return matching_entity_ids
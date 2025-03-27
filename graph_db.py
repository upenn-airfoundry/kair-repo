############
## Basic database "graph" interface
##
############


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
        
    def add_paper(self, url: str, crawl_time: str, title: str, summary: str) -> int:
        """Store a paper by URL and return its paper ID."""
        with self.conn.cursor() as cur:
            # See if paper already exists
            cur.execute("SELECT id FROM papers WHERE url = %s AND crawl_time = %s;", (url, crawl_time))
            paper_id = cur.fetchone()
            if paper_id is not None:
                paper_id = paper_id[0]
                
                cur.execute("SELECT tag_value FROM paper_tags WHERE paper_id = %s AND tag_name = %s;", (paper_id, "summary"))
                the_tag = cur.fetchone()
                if the_tag is None:
                    cur.execute("INSERT INTO paper_tags (paper_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self._generate_embedding(summary)))
            
            cur.execute("INSERT INTO papers (url, crawl_time, title) VALUES (%s, %s, %s) RETURNING id;", (url,crawl_time,title))
            paper_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO paper_tags (paper_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self._generate_embedding(summary)))
        self.conn.commit()
        return paper_id
    
    def update_paper(self, paper_id: int, url: Optional[str] = None, crawl_time: Optional[str] = None):
        """Update all fields of a paper given its ID."""
        with self.conn.cursor() as cur:
            if url is not None:
                cur.execute("UPDATE papers SET url = %s WHERE id = %s;", (url, paper_id))
            if crawl_time is not None:
                cur.execute("UPDATE papers SET crawl_time = %s WHERE id = %s;", (crawl_time, paper_id))
        self.conn.commit()

    def fetch_paper_paragraphs(self, paper_id: int) -> List[str]:
        """Fetch a paper's paragraphs by paper ID."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT content FROM paragraphs WHERE paper_id = %s;", (paper_id,))
            paragraphs = [row[0] for row in cur.fetchall()]
        return paragraphs

    def add_source(self, url: str) -> int:
        """Add a source by URL and return its source ID."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO sources (url) VALUES (%s) RETURNING id;", (url,))
            source_id = cur.fetchone()[0]
        self.conn.commit()
        return source_id

    def link_source_to_paper(self, source_id: int, paper_id: int):
        """Link a source ID to a paper ID."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO paper_sources (source_id, paper_id) VALUES (%s, %s);", (source_id, paper_id))
        self.conn.commit()

    def link_author_to_paper(self, author_id: int, paper_id: int):
        """Link an author ID to a paper ID."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO paper_authors (paper_id, author_id) VALUES (%s, %s);", (paper_id, author_id))
        self.conn.commit()

    def add_paragraph(self, paper_id: int, content: str) -> Tuple[List[float], int]:
        """Add a paragraph, returning an embedding and paragraph ID."""
        embedding = self._generate_embedding(content)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO paragraphs (paper_id, paragraph_text, embedding) VALUES (%s, %s, %s) RETURNING paragraph_id;",
                (paper_id, content, embedding)
            )
            paragraph_id = cur.fetchone()[0]
        self.conn.commit()
        return embedding, paragraph_id
    
    def add_author(self, name: str, email: str, organization: str) -> int:
        """Add an author by name and return their author ID."""
        with self.conn.cursor() as cur:
            # Check if the author already exists
            cur.execute("SELECT author_id FROM authors WHERE author_name = %s;", (name,))
            author_id = cur.fetchone()
            if author_id is None:
                # Add the author if they don't exist
                cur.execute("INSERT INTO authors (author_name) VALUES (%s) RETURNING author_id;", (name,))
                author_id = cur.fetchone()[0]
            if email is not None:
                cur.execute("UPDATE authors SET email = %s WHERE author_id = %s;", (email, author_id))
            if organization is not None:
                cur.execute("UPDATE authors SET organization = %s WHERE author_id = %s;", (organization, author_id))
        self.conn.commit()
        return author_id

    def update_paragraph(self, paragraph_id: int, content: Optional[str] = None, embedding: Optional[List[float]] = None):
        """Update all fields of a paragraph given its ID."""
        with self.conn.cursor() as cur:
            if content is not None:
                cur.execute("UPDATE paragraphs SET paragraph_text = %s WHERE id = %s;", (content, paragraph_id))
            if embedding is not None:
                cur.execute("UPDATE paragraphs SET embedding = %s WHERE id = %s;", (embedding, paragraph_id))
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
            cur.execute("SELECT tag_value FROM paper_tags WHERE paper_id = %s AND tag_name = %s;", (paper_id, tag))
            the_tag = cur.fetchone()
            if the_tag is None:
                cur.execute("INSERT INTO paper_tags (paper_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paper_id, tag, tag_value))
            else:
                # Update the tag if it already exists
                cur.execute("UPDATE paper_tags SET tag_value = %s WHERE paper_id = %s AND tag_name = %s;", (tag_value, paper_id, tag))
        self.conn.commit()

    def find_paragraphs_by_tag(self, tag: str) -> List[int]:
        """Find all paragraph matches to a tag."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT paragraph_id FROM paragraph_tags WHERE tag = %s;", (tag,))
            paragraph_ids = [row[0] for row in cur.fetchall()]
        return paragraph_ids

    def find_tags_for_paragraph(self, paragraph_id: int) -> List[str]:
        """Find all tags for a paragraph."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT tag FROM paragraph_tags WHERE paragraph_id = %s;", (paragraph_id,))
            tags = [row[0] for row in cur.fetchall()]
        return tags

    def find_k_most_similar_paragraphs(self, paragraph_id: int, k: int) -> List[int]:
        """Find the k most similar paragraphs given a paragraph."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT embedding FROM paragraphs WHERE id = %s;", (paragraph_id,))
            embedding = cur.fetchone()[0]
            cur.execute(
                """
                SELECT id FROM paragraphs
                WHERE id != %s
                ORDER BY (embedding <-> %s) ASC
                LIMIT %s;
                """,
                (paragraph_id, embedding, k)
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
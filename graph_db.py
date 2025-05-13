############
## Basic database "graph" interface wrapper, currently
## using TimescaleDB because of scalable pgvectorscale
## implementation and hybrid relational/graph capabilities.
##
## Copyright (C) Zachary G. Ives, 2025
##################

import psycopg2
from psycopg2.extras import execute_values
import os
from typing import List, Tuple, Optional, Any
import pandas as pd
import uuid

from langchain_openai.embeddings import OpenAIEmbeddings

import logging

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
        self.schema = os.getenv("DB_SCHEMA", "public")
        
    def exec_sql(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        """Execute an SQL query and return the results."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        except Exception as e:
            logging.error(f"Error executing SQL: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        
    def execute(self, sql: str, params: Tuple = ()):
        """Execute an SQL query and return the results."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
        except Exception as e:
            logging.error(f"Error executing SQL: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
            
    def commit(self):
        """Commit the current transaction."""
        self.conn.commit()
        
    def exists_document(self, url: str) -> bool:
        """Check if a paper exists in the database by URL."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT entity_id FROM entities WHERE entity_url = %s;", (url, ))
                result = cur.fetchone()
                return result is not None
        except Exception as e:
            logging.error(f"Error checking paper existence: {e}")
            return False
        finally:
            self.conn.rollback()
        
    def add_paper(self, url: str, title: str, summary: str) -> int:
        """Store a paper by URL and return its paper ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_name = %s AND entity_type = 'paper';", (title,))
                paper_id = cur.fetchone()
                if paper_id is not None:
                    paper_id = paper_id[0]
                    cur.execute(f"SELECT tag_value FROM {self.schema}.entity_tags WHERE entity_id = %s AND tag_name = %s;", (paper_id, "summary"))
                    the_tag = cur.fetchone()
                    if the_tag is None:
                        cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self.generate_embedding(summary)))
                else:
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_url, entity_type, entity_name) VALUES (%s, %s, %s) RETURNING entity_id;", (url, 'paper', title))
                    paper_id = cur.fetchone()[0]
                    cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self.generate_embedding(summary)))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding paper: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        return paper_id

    def get_table_info(self, url: str) -> dict:
        """Store a table by URL and return its entity ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id, entity_type, entity_name, entity_url, entity_json FROM {self.schema}.entities WHERE entity_name = %s AND entity_type = 'table';", (path,))
                result = cur.fetchone()
                if result is not None:
                    # Return
                    return {
                        "entity_id": result[0],
                        "entity_type": result[1],
                        "entity_name": result[2],
                        "entity_url": result[3],
                        "entity_json": result[4]
                    }
                else:
                    # Return None if not found
                    return None
        except Exception as e:
            logging.error(f"Error adding table: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
    

    def add_table(self, url: str, path: str, summary: str) -> int:
        """Store a table by URL and return its entity ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_name = %s AND entity_type = 'table';", (path,))
                table_id = cur.fetchone()
                if table_id is not None:
                    table_id = table_id[0]
                    cur.execute(f"SELECT tag_value FROM {self.schema}.entity_tags WHERE entity_id = %s AND tag_name = %s;", (table_id, "summary"))
                    the_tag = cur.fetchone()
                    if the_tag is None:
                        cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (table_id, "summary", summary, self.generate_embedding(summary)))
                else:
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_url, entity_type, entity_name) VALUES (%s, %s, %s) RETURNING entity_id;", (url, 'table', path))
                    table_id = cur.fetchone()[0]
                    cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (table_id, "summary", summary, self.generate_embedding(summary)))
                self.conn.commit()
                return table_id
        except Exception as e:
            logging.error(f"Error adding table: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
    
    def update_paper(self, paper_id: int, url: Optional[str] = None, crawl_time: Optional[str] = None):
        """Update all fields of a paper given its ID."""
        try:
            with self.conn.cursor() as cur:
                if url is not None:
                    cur.execute(f"UPDATE {self.schema}.entities SET url = %s WHERE entity_id = %s;", (url, paper_id))
                if crawl_time is not None:
                    cur.execute(f"UPDATE {self.schema}.entities SET crawl_time = %s WHERE entity_id = %s;", (crawl_time, paper_id))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error updating paper: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def fetch_paper_paragraphs(self, paper_id: int) -> List[str]:
        """Fetch a paper's paragraphs by paper ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_detail FROM {self.schema}.entities WHERE entity_type = 'paragraph' and entity_parent = %s;", (paper_id,))
                paragraphs = [row[0] for row in cur.fetchall()]
            return paragraphs
        except Exception as e:
            logging.error(f"Error fetching paper paragraphs: {e}")
            self.conn.rollback()
            return []
        
    def delete_paragraphs(self, paper_id: int):
        """Delete all paragraphs for a given paper ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"DELETE FROM {self.schema}.entities WHERE entity_parent = %s AND entity_type = 'paragraph';", (paper_id,))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error deleting paragraphs: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def add_source(self, url: str) -> int:
        """Add a source by URL and return its source ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_url) VALUES (%s,%s) RETURNING entity_id;", ('source', url,))
                source_id = cur.fetchone()[0]
            self.conn.commit()
            return source_id
        except Exception as e:
            logging.error(f"Error adding source: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        
        
    def add_person(self, url: str, source_type: str, name: str, affiliation: str, author_json, disambiguator: Optional[str] = None) -> int:
        """
        Add an author with a name and an optional disambiguating identifier.
        If the author already exists, return the existing entity ID.

        Args:
            name (str): The name of the author.
            url (str): The URL of the author's profile, whether a homepage or a Google Scholar entry.
            disambiguator (Optional[str]): An optional disambiguating identifier.

        Returns:
            int: The entity_id of the inserted or existing author.
        """
        # Concatenate the disambiguator to the name if provided
        full_name = f"{name} #{disambiguator}" if disambiguator is not None else name

        embed = self.generate_embedding(f"{name} at {affiliation}")
        try:
            with self.conn.cursor() as cur:
                # Check if the author already exists
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_type = 'author' AND entity_name = %s;", (full_name,))
                author_id = cur.fetchone()

                if author_id is not None:
                    # Author already exists, return the existing entity ID
                    return author_id[0]

                # Insert the new author into the entities table
                cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_name, entity_url, entity_json, entity_embed) VALUES (%s, %s, %s, %s, %s) RETURNING entity_id;", (source_type, full_name, url, author_json, embed ))
                author_id = cur.fetchone()[0]

            self.conn.commit()
            return author_id

        except Exception as e:
            logging.error(f"Error adding author with disambiguator: {e}")
            self.conn.rollback()
            raise e

    def link_source_to_paper(self, source_id: int, paper_id: int):
        """Link a source ID to a paper ID."""
        try:
            with self.conn.cursor() as cur:
                # Check if the link already exists
                cur.execute(f"SELECT 1 FROM {self.schema}.entity_link WHERE from_id = %s AND to_id = %s;", (source_id, paper_id))
                the_link = cur.fetchone()
                if the_link is None:
                    cur.execute(f"INSERT INTO {self.schema}.entity_link (from_id, to_id, entity_strength, link_type) VALUES (%s, %s, 'source');", (source_id, paper_id,1))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error linking source to paper: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def link_author_to_paper(self, author_id: int, paper_id: int):
        """Link an author ID to a paper ID."""
        try:
            with self.conn.cursor() as cur:
                # Check if the link already exists
                cur.execute(f"SELECT 1 FROM {self.schema}.entity_link WHERE from_id = %s AND to_id = %s;", (author_id, paper_id))
                the_link = cur.fetchone()
                if the_link is None:
                    cur.execute(f"INSERT INTO {self.schema}.entity_link (from_id, to_id, entity_strength, link_type) VALUES (%s, %s, %s, 'author');", (author_id, paper_id, 1))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error linking author to paper: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def add_paragraph(self, paper_id: int, content: str) -> Tuple[List[float], int]:
        """Add a paragraph, returning an embedding and paragraph ID."""
        try:
            embedding = self.generate_embedding(content)
            with self.conn.cursor() as cur:
                # Check if the paragraph already exists
                content = content.replace("\x00", "\uFFFD")
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_parent = %s AND entity_type = 'paragraph' AND entity_detail = %s;", (paper_id, content,))
                paragraph_id = cur.fetchone()
                if paragraph_id is None:
                    cur.execute(
                        f"INSERT INTO {self.schema}.entities (entity_parent, entity_type, entity_detail, entity_embed) VALUES (%s, 'paragraph', %s, %s) RETURNING entity_id;",
                        (paper_id, content, embedding)
                    )
                    paragraph_id = cur.fetchone()[0]
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding paragraph: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        return embedding, paragraph_id
    
    def add_author(self, name: str, email: str, organization: str) -> int:
        """Add an author by name and return their author ID."""
        try:
            with self.conn.cursor() as cur:
                # Check if the author already exists
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_type = 'author' and entity_name = %s;", (name,))
                author_id = cur.fetchone()
                if author_id is None:
                    # Add the author if they don't exist
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_name) VALUES (%s, %s) RETURNING entity_id;", ('author', name,))
                    author_id = cur.fetchone()[0]
                if email is not None:
                    cur.execute(f"UPDATE {self.schema}.entities SET entity_contact = %s WHERE entity_id = %s;", (email, author_id))
                if organization is not None:
                    cur.execute(f"UPDATE {self.schema}.entities SET entity_detail = %s WHERE entity_id = %s;", (organization, author_id))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding author: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        return author_id

    def update_paragraph(self, paragraph_id: int, content: Optional[str] = None, embedding: Optional[List[float]] = None):
        """Update all fields of a paragraph given its ID."""
        try:
            with self.conn.cursor() as cur:
                if content is not None:
                    cur.execute(f"UPDATE {self.schema}.entities SET entity_detail = %s WHERE entity_id = %s;", (content, paragraph_id))
                if embedding is not None:
                    cur.execute(f"UPDATE {self.schema}.entities SET entity_embed = %s WHERE entity_id = %s;", (embedding, paragraph_id))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error updating paragraph: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
            
    def add_tag_to_paragraph(self, paragraph_id: int, tag: str, tag_value: str):
        """Add a tag to a paragraph."""
        try:
            with self.conn.cursor() as cur:
                # Check if the tag already exists
                cur.execute(f"SELECT tag_value FROM {self.schema}.paragraph_tags WHERE paragraph_id = %s AND tag_name = %s;", (paragraph_id, tag))
                the_tag = cur.fetchone()
                if the_tag is None:
                    cur.execute(f"INSERT INTO {self.schema}.paragraph_tags (paragraph_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paragraph_id, tag, tag_value))
                else:
                    # Update the tag if it already exists
                    cur.execute(f"UPDATE {self.schema}.paragraph_tags SET tag_value = %s WHERE paragraph_id = %s AND tag_name = %s;", (tag_value, paragraph_id, tag))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding tag to paragraph: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def add_tag_to_entity(self, paper_id: int, tag: str, tag_value: str):
        """Add a tag to a paper."""
        try:
            with self.conn.cursor() as cur:
                # Check if the tag already exists
                cur.execute(f"SELECT tag_value FROM {self.schema}.entity_tags WHERE entity_id = %s AND tag_name = %s;", (paper_id, tag))
                the_tag = cur.fetchone()
                if the_tag is None:
                    cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paper_id, tag, tag_value))
                else:
                    # Update the tag if it already exists
                    cur.execute(f"UPDATE {self.schema}.entity_tags SET tag_value = %s WHERE entity_id = %s AND tag_name = %s;", (tag_value, paper_id, tag))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding tag to entity: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def find_paragraphs_by_tag(self, tag: str) -> List[int]:
        """Find all paragraph matches to a tag."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id FROM {self.schema}.entity_tags WHERE tag_name = %s AND entity_type = 'paragraph';", (tag,))
                paragraph_ids = [row[0] for row in cur.fetchall()]
            return paragraph_ids
        except Exception as e:
            logging.error(f"Error finding paragraphs by tag: {e}")
            self.conn.rollback()
            return []

    def find_tags_for_paragraph(self, paragraph_id: int) -> List[str]:
        """Find all tags for a paragraph."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT tag_name FROM {self.schema}.entity_tags WHERE entity_id = %s;", (paragraph_id,))
                tags = [row[0] for row in cur.fetchall()]
            return tags
        except Exception as e:
            logging.error(f"Error finding tags for paragraph: {e}")
            self.conn.rollback()
            return []

    def find_k_most_similar_entities(self, entity_id: int, k: int) -> List[int]:
        """Find the k most similar entities given an entity."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT entity_embed FROM entities WHERE entity_id = %s;", (entity_id,))
                embedding = cur.fetchone()[0]
                cur.execute(
                    f"""
                    SELECT id FROM {self.schema}.entities
                    WHERE entity_id != %s
                    ORDER BY (entity_embed <-> %s::vector) ASC
                    LIMIT %s;
                    """,
                    (entity_id, str(embedding), k)
                )
                similar_paragraph_ids = [row[0] for row in cur.fetchall()]
            return similar_paragraph_ids
        except Exception as e:
            logging.error(f"Error finding similar entities: {e}")
            self.conn.rollback()
            return []

    def generate_embedding(self, content: str) -> List[float]:
        """Generate an embedding for the given content using LangChain and OpenAI."""
        try:
            # Initialize OpenAI embeddings
            embeddings = OpenAIEmbeddings()
            # Generate the embedding for the content
            embedding = embeddings.embed_query(content)
            return embedding
        except Exception as e:
            logging.error(f"Error generating embedding: {e}")
            return [0.0] * 1536  # Return a zero vector as a fallback
        
    def add_to_crawl_queue(self, url: str):
        """Add a paper URL to the crawl queue."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"INSERT INTO {self.schema}.crawl_queue (url) VALUES (%s);", (url,))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding to crawl queue: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def fetch_next_from_crawl_queue(self) -> Optional[str]:
        """Fetch the next URL from the crawl queue."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT url FROM {self.schema}.crawl_queue ORDER BY id ASC LIMIT 1;")
                result = cur.fetchone()
                if result:
                    cur.execute(f"DELETE FROM {self.schema}.crawl_queue WHERE url = %s;", (result[0],))
                    self.conn.commit()
                    return result[0]
            return None
        except Exception as e:
            logging.error(f"Error fetching from crawl queue: {e}")
            self.conn.rollback()
            return None

    def find_related_entities(self, question: str, k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[str]:
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
        concept_embedding = self.generate_embedding(question)
        return self.find_related_entities_by_embedding(concept_embedding, k, entity_type, keywords)

    def find_related_entity_ids(self, question: str, k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[int]:
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
        concept_embedding = self.generate_embedding(question)
        return self.find_related_entity_ids_by_embedding(concept_embedding, k, entity_type, keywords)

    def find_related_entity_ids_by_tag(self, tag_value: str, tag_name: str = None, k: int = 10) -> List[int]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.
        Args:
            tag_name (str): The name of the tag to filter by.
            k (int): The number of closest matches to return.
        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query_embedding = self.generate_embedding(tag_value)
        return self.find_entity_ids_by_tag_embedding(query_embedding, tag_name, k)

    def find_related_entities_by_tag(self, tag_value: str, tag_name: str = None, k: int = 10) -> List[str]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.
        Args:
            tag_name (str): The name of the tag to filter by.
            k (int): The number of closest matches to return.
        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query_embedding = self.generate_embedding(tag_value)
        return self.find_entities_by_tag_embedding(query_embedding, tag_name, k)

    def find_related_entities_by_embedding(self, concept_embedding: List[float], k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[str]:
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
        query = f"""
            SELECT entity_type || ': ' || COALESCE(entity_name, entity_detail)
            FROM {self.schema}.entities
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
        
        logging.debug("Query: ", query)

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, tuple(params))
                related_entity_ids = [row[0] for row in cur.fetchall()]

            return related_entity_ids
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            self.conn.rollback()
            return []
        
    def find_related_entity_ids_by_embedding(self, concept_embedding: List[float], k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[str]:
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
        query = f"""
            SELECT entity_id
            FROM {self.schema}.entities
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
        
        logging.debug("Query: ", query)

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, tuple(params))
                related_entity_ids = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            self.conn.rollback()
            return []

        return related_entity_ids

    def find_entities_by_tag_embedding(self, query_embedding: List[float], tag_name: str, k: int = 10) -> List[str]:
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
        if tag_name:
            query = f"""
                SELECT tag_name || ': ' || COALESCE(entity_name, entity_detail)
                FROM {self.schema}.entity_tags JOIN {self.schema}.entities ON entity_tags.entity_id = entities.entity_id
                WHERE tag_name = %s
                ORDER BY (tag_embed <-> %s::vector) ASC
                LIMIT %s;
            """
            params = (tag_name, str(query_embedding), k)
        else:
            query = f"""
                SELECT tag_name || ': ' || COALESCE(entity_name, entity_detail)
                FROM {self.schema}.entity_tags JOIN {self.schema}.entities ON entity_tags.entity_id = entities.entity_id
                ORDER BY (tag_embed <-> %s::vector) ASC
                LIMIT %s;
            """
            params = (str(query_embedding), k)

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                matching_entity_ids = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            self.conn.rollback()
            return []

        return matching_entity_ids
    
    def find_entity_ids_by_tag_embedding(self, query_embedding: List[float], tag_name: str, k: int = 10) -> List[int]:
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
        if tag_name:
            query = f"""
                SELECT entities.entity_id
                FROM {self.schema}.entity_tags JOIN {self.schema}.entities ON entity_tags.entity_id = entities.entity_id
                WHERE tag_name = %s
                ORDER BY (tag_embed <-> %s::vector) ASC
                LIMIT %s;
            """
            params = (tag_name, str(query_embedding), k)
        else:
            query = f"""
                SELECT entities.entity_id
                FROM {self.schema}.entity_tags JOIN {self.schema}.entities ON entity_tags.entity_id = entities.entity_id
                ORDER BY (tag_embed <-> %s::vector) ASC
                LIMIT %s;
            """
            params = (str(query_embedding), k)

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                matching_entity_ids = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            self.conn.rollback()
            return []

        return matching_entity_ids
    
    def get_assessment_criteria(self, name:str = None) -> List:
        """
        Fetch all assessment criteria, or criteria with a particular name.
        """
        criteria = None
        try:
            with self.conn.cursor() as cur:
                if name is None:
                    criteria = cur.execute(f"""
                                        SELECT criteria_id, criteria_name, criteria_prompt, criteria_scope 
                                        FROM {self.schema}.assessment_criteria ORDER BY criteria_promise DESC;""")
                else:
                    criteria = cur.execute(f"""SELECT criteria_id, criteria_name, criteria_prompt, criteria_scope 
                                        FROM {self.schema}.assessment_criteria 
                                        WHERE criteria_name = %s ORDER BY criteria_promise DESC;""", \
                                            (name,))
                    
                result = [{"id": c[0], "name": c[1], "prompt": c[2], "scope": c[3]} for c in cur.fetchall()]
            return result
        except Exception as e:
            logging.error(f"Error fetching assessment criteria: {e}")
            self.conn.rollback()
            return []
    
    def add_assessment_criterion(self, name:str, prompt:str, scope: str, promise:float = 1) -> int:
        """
        Add an assessment criterion to the database.
        """
        embed = self.generate_embedding(prompt)
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""INSERT INTO {self.schema}.assessment_criteria 
                            (criteria_name, criteria_prompt, criteria_scope, criteria_promise, criteria_embed) 
                            VALUES (%s, %s, %s, %s, %s) 
                            RETURNING criteria_id;""", (name, prompt, scope, promise, embed))
                criterion_id = cur.fetchone()[0]
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding assessment criterion: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        return criterion_id
    
    def add_association_criterion(self, name: str, entity1_scope: str, entity2_scope: str, prompt: str, promise: float = 1.0) -> int:
        """
        Add an association criterion to the database.  An association criterion links two entities together... 
        with an association.

        Args:
            name (str): The name of the association criterion.
            entity1_scope (str): The scope of the first entity.
            entity2_scope (str): The scope of the second entity.
            prompt (str): The prompt for the association criterion.
            promise (float): The promise value for the association criterion (default is 1.0).

        Returns:
            int: The ID of the newly created association criterion.
        """
        embed = self.generate_embedding(prompt)
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {self.schema}.association_criteria 
                    (association_criteria_name, entity1_scope, entity2_scope, association_criteria_prompt, association_promise, association_embed) 
                    VALUES (%s, %s, %s, %s, %s, %s) 
                    RETURNING association_criteria_id;
                """, (name, entity1_scope, entity2_scope, prompt, promise, embed))
                criterion_id = cur.fetchone()[0]
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding association criterion: {e}")
            self.conn.rollback()
            raise e
        return criterion_id    
    
    def get_entities_with_summaries(self, entity_ids: Optional[List[int]] = None) -> List[dict]:
        """
        Fetch all entities and their associated 'summary' tags, filtered by a list of entity IDs if provided.

        Args:
            entity_ids (Optional[List[int]]): A list of entity IDs to filter the results. If None, fetch all entities.

        Returns:
            List[dict]: A list of dictionaries containing entity names and their summaries.
        """
        query = f"""
            SELECT e.entity_name, t.tag_value AS summary
            FROM {self.schema}.entities e
            LEFT JOIN {self.schema}.entity_tags t ON e.entity_id = t.entity_id AND t.tag_name = 'summary'
            WHERE e.entity_name IS NOT NULL
        """
        params = []

        # Add filtering by entity_ids if provided
        if entity_ids:
            list_of_ids = ', '.join(map(str, entity_ids))
        
            query += " AND e.entity_id IN (" + list_of_ids + ")"
            # params.append(entity_ids)

        query += " ORDER BY e.entity_name ASC;"
        
        logging.debug("Query: ", query)

        try:
            results = self.exec_sql(query, ())#params)
            results = [{"name": row[0], "summary": row[1]} for row in results]
        except Exception as e:
            logging.error(f"Error getting entities with summaries: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
             
        return results
    
    def get_papers_by_field(self, field: str, k: int = 1):
        """
        Take the field, generate its embedding, match it against entity_tags of type 'field',
        and find the corresponding 'paper' entities. Print the paper IDs.

        Args:
            field (str): The field to search for.
        """
        try:
            # Generate the embedding for the given field
            field_embedding = self.generate_embedding(field)

            # Query to match the field embedding against entity_tags of type 'field'
            query = f"""
                SELECT p.entity_id, p.entity_name, t.tag_value
                FROM {self.schema}.entities p
                JOIN {self.schema}.entity_tags t ON p.entity_id = t.entity_id
                WHERE t.tag_name = 'field'
                ORDER BY (t.tag_embed <-> %s::vector) ASC
                LIMIT %s;
            """
            
            results = self.exec_sql(query, (str(field_embedding), k))
        
            return [{'entity_id': r[0], 'entity_name': r[1], 'tag_value': r[2]} for r in results]
            
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            self.conn.rollback()

    def get_untagged_papers_by_field(self, field: str, tag: str, k: int = 1):
        """
        Take the field, generate its embedding, match it against entity_tags of type 'field',
        and find the corresponding 'paper' entities. Print the paper IDs.

        Args:
            field (str): The field to search for.
            tag (str): The tag to exclude from the search.
            k (int): The number of results to return.
        Returns:
            List[dict]: A list of dictionaries containing entity IDs, names, and tag values.
        """
        try:
            # Generate the embedding for the given field
            field_embedding = self.generate_embedding(field)

            # Query to match the field embedding against entity_tags of type 'field'
            query = f"""
                SELECT p.entity_id, p.entity_name, t.tag_value
                FROM {self.schema}.entities p
                JOIN {self.schema}.entity_tags t ON p.entity_id = t.entity_id
                WHERE t.tag_name = 'field' AND NOT EXISTS (select * from entity_tags t2 where t2.entity_id = p.entity_id and t2.tag_name = %s)
                ORDER BY (t.tag_embed <-> %s::vector) ASC
                LIMIT %s;
            """
            with self.conn.cursor() as cur:
                results = self.exec_sql(query, (tag, str(field_embedding), k))
            
                return [{'entity_id': r[0], 'entity_name': r[1], 'tag_value': r[2]} for r in results]
            
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            self.conn.rollback()

    def get_entities_from_db(self, paper_id: int):

        query = f"""
            SELECT entity_id, paper, array_agg('{ "name": "' || coalesce(author,'') || '", "email": "' || coalesce(email,'') || '", "detail": "' || coalesce(source,'') || '" }') AS authors
                        FROM (
                        SELECT p.entity_id, '"title": "' || p.entity_name || '", "abstract": "' || summary.tag_value || '", "field": "' || fields.tag_value || '"' AS paper, target.entity_name AS author, replace(target.entity_detail,'"','') AS source, target.entity_contact as email
                        FROM {self.schema}.entities p JOIN entity_tags summary ON p.entity_id = summary.entity_id
                        JOIN {self.schema}.entity_tags fields ON p.entity_id = fields.entity_id
                        JOIN {self.schema}.entity_link ON p.entity_id = entity_link.to_id
                        JOIN {self.schema}.entities AS target ON entity_link.from_id = target.entity_id
                        WHERE summary.tag_name = 'summary' AND fields.tag_name = 'field'
                        AND p.entity_id = %s
                        AND p.entity_type = 'paper' AND target.entity_type = 'author'
                    ) GROUP BY entity_id, paper;
        """    
        try:
            result = self.exec_sql(query, (paper_id,))
            new_results = []
            for row in result:
                (paper_id, paper_desc, nested) = row
                
                n = '['
                for n2 in nested:
                    n += n2 + ', '
                n = n[:-2] + ']'
                
                description = '{' + paper_desc.replace('\n', ' ').replace('\r', ' ') + ', "authors": ' + n.replace('\n', ' ').replace('\r', ' ') + '}'
                new_results.append({"id": paper_id, "json": description})
                # print(f"Paper ID: {paper_id}, Description: {description}")
            return new_results
        except Exception as e:
            logging.error(f"Error fetching entities from DB: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e

    def get_untagged_entities_as_json(self, paper_id: int, tag: str):

        query = f"""
            SELECT entity_id, paper, array_agg('{ "name": "' || coalesce(author,'') || '", "email": "' || coalesce(email,'') || '", "detail": "' || coalesce(source,'') || '" }') AS authors
                        FROM (
                        SELECT p.entity_id, '"title": "' || p.entity_name || '", "abstract": "' || summary.tag_value || '", "field": "' || fields.tag_value || '"' AS paper, target.entity_name AS author, replace(target.entity_detail,'"','') AS source, target.entity_contact as email
                        FROM {self.schema}.entities p JOIN entity_tags summary ON p.entity_id = summary.entity_id
                        JOIN {self.schema}.entity_tags fields ON p.entity_id = fields.entity_id
                        JOIN {self.schema}.entity_link ON p.entity_id = entity_link.to_id
                        JOIN {self.schema}.entities AS target ON entity_link.from_id = target.entity_id
                        WHERE summary.tag_name = 'summary' AND fields.tag_name = 'field'
                        AND p.entity_id = %s AND NOT EXISTS (select * from entity_tags t2 where t2.entity_id = p.entity_id and t2.tag_name = %s)
                        AND p.entity_type = 'paper' AND target.entity_type = 'author'
                    ) GROUP BY entity_id, paper;
        """    
        try:
            result = self.exec_sql(query, (paper_id,tag))
            new_results = []
            for row in result:
                (paper_id, paper_desc, nested) = row
                
                n = '['
                for n2 in nested:
                    n += n2 + ', '
                n = n[:-2] + ']'
                
                description = '{' + paper_desc.replace('\n', ' ').replace('\r', ' ') + ', "authors": ' + n.replace('\n', ' ').replace('\r', ' ') + '}'
                new_results.append({"id": paper_id, "json": description})
                # print(f"Paper ID: {paper_id}, Description: {description}")
            return new_results
        except Exception as e:
            logging.error(f"Error fetching untagged entities: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        
    def link_entity_to_document(self, entity_id: int, indexed_url: str, indexed_path: str, indexed_type: str = 'pdf', 
                                summary: str = None): 
        """
        Link an entity to a document in the database.

        Args:
            entity_id (int): The ID of the entity to link.
            indexed_url (str): The URL of the document.
            indexed_path (str): The path of the document.
            indexed_type (str): The type of the document (default is 'pdf').
            summary (str): An optional summary of the document.
        """
        try:
            indexed_embed = ''
            if summary:
                indexed_embed = self.generate_embedding(summary)
            else:
                indexed_embed = self.generate_embedding(indexed_path.split('/')[-1])
            with self.conn.cursor() as cur:
                # Check if the link already exists
                cur.execute("SELECT 1 FROM indexed_documents WHERE entity_id = %s;", (entity_id, ))
                the_link = cur.fetchone()
                if the_link is None:
                    # TODO: add JSON?
                    cur.execute("INSERT INTO indexed_documents (entity_id, document_name, document_url, document_type, document_json, document_embed) VALUES (%s, %s, %s, %s, %s, %s);", (entity_id, indexed_path, indexed_url, indexed_type, None, indexed_embed))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error linking entity to document: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        
    def index_dataframe(self, df: pd.DataFrame, entity_id: int) -> str:
        """
        Index a Pandas DataFrame by creating a new table in the indexed_tables schema
        and adding a row to the indexed_tables table in the public schema.

        Args:
            df (pd.DataFrame): The Pandas DataFrame to index.
            entity_id (int): The entity ID to associate with the table.

        Returns:
            str: The name of the created table (unique ID).
        """
        # Generate a unique table name
        table_name = f"table_{uuid.uuid4().hex[:8]}"

        try:
            with self.conn.cursor() as cur:
                # Create the table in the indexed_tables schema
                create_table_query = f"""
                    CREATE TABLE indexed_tables.{table_name} (
                        {', '.join([f'"{col}" {self._get_sql_type(dtype)}' for col, dtype in zip(df.columns, df.dtypes)])}
                    );
                """
                cur.execute(create_table_query)

                # Insert the DataFrame data into the new table
                insert_query = f"""
                    INSERT INTO indexed_tables.{table_name} ({', '.join([f'"{col}"' for col in df.columns])})
                    VALUES %s;
                """#({', '.join(['%s' for _ in df.columns])});
                
                # for _, row in df.iterrows():
                    # cur.execute(insert_query, tuple(row))
                data_to_insert = [tuple(row) for row in df.values.tolist()]
                execute_values(cur, insert_query, data_to_insert)

                # Add a row to the indexed_tables table in the public schema
                cur.execute("""
                    INSERT INTO indexed_tables (entity_id, table_name, table_type)
                    VALUES (%s, %s, %s);
                """, (entity_id, table_name, 'dataframe'))

            # Commit the transaction
            self.conn.commit()

        except Exception as e:
            logging.error(f"Error indexing DataFrame: {e}")
            self.conn.rollback()
            raise e

        return table_name

    def _get_sql_type(self, dtype: Any) -> str:
        """
        Map Pandas data types to SQL data types.

        Args:
            dtype (pd.api.types.DtypeObj): The Pandas data type.

        Returns:
            str: The corresponding SQL data type.
        """
        if pd.api.types.is_integer_dtype(dtype):
            return "INTEGER"
        elif pd.api.types.is_float_dtype(dtype):
            return "DOUBLE PRECISION"
        elif pd.api.types.is_bool_dtype(dtype):
            return "BOOLEAN"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            return "TIMESTAMP"
        else:
            return "TEXT"
    

    def add_task_to_queue(self, name: str, scope: str, prompt: str, description: str) -> int:
        """
        Add a task to the task_queue relation.

        Args:
            name (str): The name of the task.
            scope (str): The scope of the task.
            prompt (str): The prompt for the task.
            description (str): A description of the task.

        Returns:
            int: The task_id of the newly added task.
        """
        query = f"""
            INSERT INTO {self.schema}.task_queue (task_name, task_scope, task_prompt, task_description)
            VALUES (%s, %s, %s, %s)
            RETURNING task_id;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (name, scope, prompt, description))
                task_id = cur.fetchone()[0]
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding task to queue: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        return task_id

    def fetch_next_task(self) -> Optional[dict]:
        """
        Fetch the next task from the task_queue in queue order.

        Returns:
            Optional[dict]: A dictionary containing the task details, or None if the queue is empty.
        """
        query = f"""
            SELECT task_id, task_name, task_scope, task_prompt, task_description
            FROM {self.schema}.task_queue
            ORDER BY task_id ASC
            LIMIT 1;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query)
                task = cur.fetchone()
                if task:
                    return {
                        "task_id": task[0],
                        "name": task[1],
                        "scope": task[2],
                        "prompt": task[3],
                        "description": task[4],
                    }
            return None
        except Exception as e:
            logging.error(f"Error fetching next task: {e}")
            self.conn.rollback()
            return None

    def delete_task(self, task_id: int):
        """
        Delete a task from the task_queue by task_id.

        Args:
            task_id (int): The ID of the task to delete.
        """
        query = f"DELETE FROM {self.schema}.task_queue WHERE task_id = %s;"
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (task_id,))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error deleting task: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
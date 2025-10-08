############
## Basic database "graph" interface wrapper, currently
## using TimescaleDB because of scalable pgvectorscale
## implementation and hybrid relational/graph capabilities.
##
## Copyright (C) Zachary G. Ives, 2025
##################

import json
import psycopg2
from psycopg2.extras import execute_values
import os
from typing import List, Tuple, Optional, Any
import pandas as pd
import uuid

try:
    from langchain_openai.embeddings import OpenAIEmbeddings
except ImportError:
    OpenAIEmbeddings = None

import logging

from dotenv import load_dotenv, find_dotenv
import hashlib
from datetime import datetime
from enrichment.llms import gemini_doc_embedding
import time

# Load environment variables from .env file
_ = load_dotenv(find_dotenv())

class GraphAccessor:
    def __init__(self):
        self.schema = os.getenv("DB_SCHEMA", "public")
        cloud_sql_conn_name = os.getenv("CLOUD_SQL_CONNECTION_NAME")
        if cloud_sql_conn_name:
            try:
                from google.cloud.sql.connector import Connector
                connector = Connector()
                self._connector = connector
                self.conn = connector.connect(
                    cloud_sql_conn_name,
                    "pg8000",
                    user=os.getenv("DB_USER"),
                    password=os.getenv("DB_PASSWORD"),
                    db=os.getenv("DB_NAME"),
                )
                self.driver = "pg8000"
            except Exception as e:
                logging.error(f"Cloud SQL connector init failed: {e}")
                raise
        else:
            self.conn = psycopg2.connect(dbname=os.getenv("DB_NAME"), \
                                user=os.getenv("DB_USER"), \
                                password=os.getenv("DB_PASSWORD"), \
                                host=os.getenv("DB_HOST", "localhost"), \
                                port=os.getenv("DB_PORT", "5432") \
            )
            self.driver = "psycopg2"
        
    def exec_sql(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        """Execute an SQL query and return the results."""
        try:
            if self.driver == "pg8000":
                # pg8000 doesn't support context managers the same way
                cur = self.conn.cursor()
                cur.execute(sql, params)
                result = cur.fetchall()
                cur.close()
                return result
            else:
                # psycopg2
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()
        except Exception as e:
            logging.error(f"Error executing SQL: {e}")
            if self.driver == "psycopg2":
                self.conn.rollback()
            # throw the exception again
            raise e
        
    def execute(self, sql: str, params: Tuple = ()):
        """Execute an SQL query and return the results."""
        try:
            if self.driver == "pg8000":
                # pg8000 doesn't support context managers the same way
                cur = self.conn.cursor()
                cur.execute(sql, params)
                cur.close()
            else:
                # psycopg2
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
        except Exception as e:
            logging.error(f"Error executing SQL: {e}")
            if self.driver == "psycopg2":
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
            
    def add_paper(self, url: str, title: str, summary: str, add_another: bool = False) -> int:
        """Store a paper by URL and return its paper ID."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_name = %s AND entity_type = 'paper';", (title,))
                paper_id = cur.fetchone()
                if paper_id is not None:
                    paper_id = paper_id[0]
                    cur.execute(f"UPDATE {self.schema}.entities SET entity_url = %s, entity_name = %s WHERE entity_id = %s;", (url, title, paper_id))
                    cur.execute(f"SELECT tag_value FROM {self.schema}.entity_tags WHERE entity_id = %s AND tag_name = %s and entity_tag_instance = 1;", (paper_id, "summary"))
                    the_tag = cur.fetchone()
                    if the_tag is None:
                        cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self.generate_embedding(summary)))
                    elif add_another:
                        # If we are adding another paper with the same title, first we need the max tag instance
                        cur.execute("SELECT MAX(entity_tag_instance) FROM entity_tags WHERE entity_id = %s AND tag_name = %s;", (paper_id, "summary"))
                        existing_tag_instance = cur.fetchone()[0] # type: ignore
                        new_tag_instance = existing_tag_instance + 1 if existing_tag_instance is not None else 1
                        cur.execute("INSERT INTO entity_tags (entity_id, tag_name, tag_value, tag_embed, entity_tag_instance) VALUES (%s, %s, %s, %s, %s);", (paper_id, "summary", summary, self.generate_embedding(summary), new_tag_instance))
                else:
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_url, entity_type, entity_name) VALUES (%s, %s, %s) RETURNING entity_id;", (url, 'paper', title))
                    paper_id = cur.fetchone()[0] # type: ignore
                    cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (paper_id, "summary", summary, self.generate_embedding(summary)))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding paper: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        return paper_id
    
    def update_paper_description(self, paper_id: int):
        """Update the description of a paper, given both the summary and author info."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    update entities
                    set entity_detail = (
                        select concat('Title: ', entities.entity_name, '\nSummary: ', et2.tag_value, '\nAuthors: ', string_agg(et.tag_value, ', ' order by et.entity_tag_instance))
                        from entity_tags et, entity_tags et2
                        where entities.entity_id = et.entity_id and entities.entity_id = et2.entity_id and entities.entity_type = 'paper' 
                        and et2.tag_name = 'summary' and et.tag_name = 'author'
                        group by entities.entity_id, entities.entity_name, et2.tag_value
                )
                where entity_id = %s and entity_type = 'paper'
            """, (paper_id,))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error updating paper description: {e}")
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
                    the_tag = cur.fetchone() # type: ignore
                    if the_tag is None:
                        cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (table_id, "summary", summary, self.generate_embedding(summary)))
                else:
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_url, entity_type, entity_name) VALUES (%s, %s, %s) RETURNING entity_id;", (url, 'table', path))
                    table_id = cur.fetchone()[0] # type: ignore
                    cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (table_id, "summary", summary, self.generate_embedding(summary)))
                self.conn.commit()
                return table_id
        except Exception as e:
            logging.error(f"Error adding table: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
    
    def update_paper(self, paper_id: int, url: Optional[str] = None, crawl_time: Optional[str] = None):
        """
        Update all fields of a paper given its ID.
        
        Unlike add_paper, we don't update any tags or embeddings associated with the paper.
        """
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
        """Fetch a paper's paragraphs by paper ID, in order."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_detail FROM {self.schema}.entities WHERE entity_type = 'paragraph' and entity_parent = %s ORDER BY entity_id;", (paper_id,))
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
        
    def add_source(self, url: str, source_type: str='source', description: Optional[str] = None) -> int:
        """Add a source by URL and return its source ID."""
        try:
            with self.conn.cursor() as cur:
                if description is None:
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_url) VALUES (%s,%s) RETURNING entity_id;", (source_type, url,))
                else:
                    cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_url, entity_name) VALUES (%s,%s,%s) RETURNING entity_id;", (source_type, url, description,))
                source_id = cur.fetchone()[0] # type: ignore
            self.conn.commit()
            return source_id
        except Exception as e:
            logging.error(f"Error adding source: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
        
    def exists_person(self, name: str, disambiguator: str, source_type: str) -> bool:
        """Check if a person exists in the database by name."""
        full_name = f"{name} #{disambiguator}" if disambiguator is not None else name
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_name = %s AND entity_type = %s;", (full_name,source_type,))
                result = cur.fetchone()
                return result is not None
        except Exception as e:
            logging.error(f"Error checking person existence: {e}")
            self.conn.rollback()
            return False


    def add_person_info_page(self, url: str, name: str, category: str, text: str):
        """
        Adds a person's info page as an entity of type 'source' to the entities table.

        Args:
            url (str): The URL of the page.
            name (str): The person's name.
            category (str): The category (will be stored in entity_contact).
            text (str): The text content (will be stored in entity_detail).
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO entities (entity_type, entity_name, entity_url, entity_detail, entity_contact)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (entity_type, entity_name, entity_url)
                    DO UPDATE SET
                        entity_detail = EXCLUDED.entity_detail,
                        entity_contact = EXCLUDED.entity_contact
                    RETURNING entity_id;
                    """,
                    ('source', name, url, text, category)
                )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding person info page: {e}")
            self.conn.rollback()
            #raise e
                
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

        # if affiliation:
        #     embed = self.generate_embedding(f"{name} at {affiliation}")
        # else:
        embed = self.generate_embedding(name)
        try:
            with self.conn.cursor() as cur:
                # Check if the author already exists
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_type = 'author' AND entity_name = %s;", (full_name,))
                author_id = cur.fetchone()

                if author_id is not None:
                    # Author already exists, return the existing entity ID
                    return author_id[0]

                # Insert the new author into the entities table
                cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_name, entity_url, entity_json, entity_embed) " +
                            """
                            VALUES (%s, %s, %s, %s, %s) 
                            ON CONFLICT (entity_type, entity_name, entity_url)
                            DO UPDATE SET
                                entity_detail = EXCLUDED.entity_detail,
                                entity_contact = EXCLUDED.entity_contact, 
                                entity_json = EXCLUDED.entity_json,
                                entity_embed = EXCLUDED.entity_embed
                        RETURNING entity_id;
                            """, (source_type, full_name, url, author_json, embed ))
                author_id = cur.fetchone()[0] # type: ignore

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
            paragraph_id = 0
            with self.conn.cursor() as cur:
                # Check if the paragraph already exists
                content = content.replace("\x00", "\uFFFD")
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_parent = %s AND entity_type = 'paragraph' AND entity_detail = %s;", (paper_id, content,))
                paragraph_id = cur.fetchone() # type: ignore
                if paragraph_id is None:
                    cur.execute(
                        f"INSERT INTO {self.schema}.entities (entity_parent, entity_type, entity_detail, entity_embed) VALUES (%s, 'paragraph', %s, %s) RETURNING entity_id;",
                        (paper_id, content, embedding)
                    )
                    paragraph_id = cur.fetchone()[0] # type: ignore
            self.conn.commit()
            return (embedding, paragraph_id) # type: ignore
        except Exception as e:
            logging.error(f"Error adding paragraph: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
    
    # def add_author(self, name: str, email: str, organization: str) -> int:
    #     """Add an author by name and return their author ID."""
    #     try:
    #         with self.conn.cursor() as cur:
    #             # Check if the author already exists
    #             cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_type = 'author' and entity_name = %s;", (name,))
    #             author_id = cur.fetchone()
    #             if author_id is None:
    #                 # Add the author if they don't exist
    #                 cur.execute(f"INSERT INTO {self.schema}.entities (entity_type, entity_name) VALUES (%s, %s) RETURNING entity_id;", ('author', name,))
    #                 author_id = cur.fetchone()[0]
    #             if email is not None:
    #                 cur.execute(f"UPDATE {self.schema}.entities SET entity_contact = %s WHERE entity_id = %s;", (email, author_id))
    #             if organization is not None:
    #                 cur.execute(f"UPDATE {self.schema}.entities SET entity_detail = %s WHERE entity_id = %s;", (organization, author_id))
    #         self.conn.commit()
    #     except Exception as e:
    #         logging.error(f"Error adding author: {e}")
    #         self.conn.rollback()
    #         # throw the exception again
    #         raise e
    #     return author_id
    
    def add_author_tag(self, paper_id: int, name: str, email: Optional[str] = None, organization: Optional[str] = None) -> int:
        """Add an author tag to a paper."""
        return self.add_or_update_tag(paper_id, "author", name, add_another=True)
        

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
            
    # def add_tag_to_paragraph(self, paragraph_id: int, tag: str, tag_value: str):
    #     """Add a tag to a paragraph."""
    #     try:
    #         with self.conn.cursor() as cur:
    #             # Check if the tag already exists
    #             cur.execute("SELECT tag_value FROM paragraph_tags WHERE paragraph_id = %s AND tag_name = %s;", (paragraph_id, tag))
    #             the_tag = cur.fetchone()
    #             if the_tag is None:
    #                 cur.execute("INSERT INTO paragraph_tags (paragraph_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paragraph_id, tag, tag_value))
    #             else:
    #                 # Update the tag if it already exists
    #                 cur.execute("UPDATE paragraph_tags SET tag_value = %s WHERE paragraph_id = %s AND tag_name = %s;", (tag_value, paragraph_id, tag))
    #         self.conn.commit()
    #     except Exception as e:
    #         logging.error(f"Error adding tag to paragraph: {e}")
    #         self.conn.rollback()
    #         # throw the exception again
    #         raise e

    def add_or_update_tag(self, entity_id: int, tag_name: str, tag_value: str, add_another: bool = True, tag_embed: Optional[List[float]] = None):
        """Add a tag to an entity.

        Depending on whether add_another is true: if the tag already exists, it will either update the (first) tag value
        or add another instance of the tag with the new value.
        """
        try:
            with self.conn.cursor() as cur:
                # Check if the tag already exists
                new_tag_instance = 1
                cur.execute(f"SELECT tag_value FROM {self.schema}.entity_tags WHERE entity_id = %s AND tag_name = %s and entity_tag_instance = 1;", (entity_id, tag_name))
                the_tag = cur.fetchone()
                if the_tag is None:
                    cur.execute(f"INSERT INTO {self.schema}.entity_tags (entity_id, tag_name, tag_value, tag_embed) VALUES (%s, %s, %s, %s);", (entity_id, tag_name, tag_value, tag_embed))
                elif not add_another:
                    # Update the tag if it already exists
                    cur.execute(f"UPDATE {self.schema}.entity_tags SET tag_value = %s WHERE entity_id = %s AND tag_name = %s and entity_tag_instance = 1;", (tag_value, entity_id, tag_name))
                else:
                    # If we are adding another paper with the same title, first we need the max tag instance
                    cur.execute("SELECT MAX(entity_tag_instance) FROM entity_tags WHERE entity_id = %s AND tag_name = %s;", (entity_id, tag_name))
                    existing_tag_instance = cur.fetchone()[0] # type: ignore
                    new_tag_instance = existing_tag_instance + 1 if existing_tag_instance is not None else 1
                    cur.execute("INSERT INTO entity_tags (entity_id, tag_name, tag_value, tag_embed, entity_tag_instance) VALUES (%s, %s, %s, %s, %s);", (entity_id, tag_name, tag_value, tag_embed, new_tag_instance))
            self.conn.commit()
            return new_tag_instance
        except Exception as e:
            logging.error(f"Error adding tag: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
            

    # def add_tag_to_entity(self, paper_id: int, tag: str, tag_value: str):
    #     """Add a tag to a paper."""
    #     try:
    #         with self.conn.cursor() as cur:
    #             # Check if the tag already exists
    #             cur.execute("SELECT tag_value FROM entity_tags WHERE entity_id = %s AND tag_name = %s;", (paper_id, tag))
    #             the_tag = cur.fetchone()
    #             if the_tag is None:
    #                 cur.execute("INSERT INTO entity_tags (entity_id, tag_name, tag_value) VALUES (%s, %s, %s);", (paper_id, tag, tag_value))
    #             else:
    #                 # Update the tag if it already exists
    #                 cur.execute("UPDATE entity_tags SET tag_value = %s WHERE entity_id = %s AND tag_name = %s;", (tag_value, paper_id, tag))
    #         self.conn.commit()
    #     except Exception as e:
    #         logging.error(f"Error adding tag to entity: {e}")
    #         self.conn.rollback()
    #         # throw the exception again
    #         raise e

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
                embedding = cur.fetchone()[0] # type: ignore
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
            if OpenAIEmbeddings is None:
                logging.error("OpenAIEmbeddings not available, using fallback")
                return [0.0] * 1536  # Return a zero vector as a fallback
            # Initialize OpenAI embeddings
            embeddings = OpenAIEmbeddings()
            #embeddings = get_embedding()
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

    def find_related_entities(self, question: str, k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[int]:
        """
        Find entities related to a particular task by matching against the entity_embed field using vector distance.
        Optionally filter by entity type and keywords.

        Args:
            question (str): The question or task to match against.
            k : The number of closest matches to return.
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
            k : The number of closest matches to return.
            entity_type (Optional[str]): The type of entities to filter by (e.g., 'paper', 'author').
            keywords (Optional[List[str]]): A list of keywords to match using tsvector.

        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        concept_embedding = self.generate_embedding(question)
        return self.find_related_entity_ids_by_embedding(concept_embedding, k, entity_type, keywords)

    def find_related_entity_ids_by_tag(self, tag_value: str, tag_name: Optional[str], k: int = 10) -> List[int]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.
        Args:
            tag_name (str): The name of the tag to filter by.
            k : The number of closest matches to return.
        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query_embedding = self.generate_embedding(tag_value)
        if tag_name is None:
            return self.find_related_entities_by_embedding(query_embedding, k)
        else:
            return self.find_entity_ids_by_tag_embedding(query_embedding, tag_name, k)

    def find_related_entities_by_tag(self, tag_value: str, tag_name: Optional[str], k: int = 10) -> List[int]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.
        Args:
            tag_name (str): The name of the tag to filter by.
            k : The number of closest matches to return.
        Returns:
            List[int]: A list of entity IDs that match the criteria.
        """
        query_embedding = self.generate_embedding(tag_value)
        if tag_name is None:
            return self.find_related_entities_by_embedding(query_embedding, k)
        else:
            return self.find_entities_by_tag_embedding(query_embedding, tag_name, k)

    def find_related_entities_by_embedding(self, concept_embedding: List[float], k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[int]] = None) -> List[int]:
        """
        Find entities related to a particular concept by matching against the entity_embed field using vector distance.
        Optionally filter by entity type and keywords.

        Args:
            concept_embedding (List[float]): The embedding of the concept to match against.
            k : The number of closest matches to return.
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
            ts_query = ' & '.join(keywords) # type: ignore
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
        
    def find_related_entity_ids_by_embedding(self, concept_embedding: List[float], k: int = 10, entity_type: Optional[str] = None, keywords: Optional[List[int]] = None) -> List[int]:
        """
        Find entities related to a particular concept by matching against the entity_embed field using vector distance.
        Optionally filter by entity type and keywords.

        Args:
            concept_embedding (List[float]): The embedding of the concept to match against.
            k : The number of closest matches to return.
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
            ts_query = ' & '.join(keywords) # type: ignore
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

    def find_entities_by_tag_embedding(self, query_embedding: List[float], tag_name: str, k: int = 10) -> List[int]:
        """
        Find entities whose tag (with a specified tag_name) has a tag_value whose embedding approximately matches
        the query embedding using vector distance.

        Args:
            query_embedding (List[float]): The embedding of the query to match against.
            tag_name (str): The name of the tag to filter by.
            k : The number of closest matches to return.

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
            k : The number of closest matches to return.

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
            if self.driver == "pg8000":
                # pg8000 doesn't support context managers the same way
                cur = self.conn.cursor()
                cur.execute(query, params)
                matching_entity_ids = [row[0] for row in cur.fetchall()]
                cur.close()
            else:
                # psycopg2
                with self.conn.cursor() as cur:
                    cur.execute(query, params)
                    matching_entity_ids = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            if self.driver == "psycopg2":
                self.conn.rollback()
            return []

        return matching_entity_ids
    
    def get_assessment_criteria(self, name:Optional[str]) -> List:
        """
        Fetch all assessment criteria, or criteria with a particular name.
        """
        criteria = None
        try:
            if self.driver == "pg8000":
                # pg8000 doesn't support context managers the same way
                cur = self.conn.cursor()
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
                cur.close()
            else:
                # psycopg2
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
            if self.driver == "psycopg2":
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
                criterion_id = cur.fetchone()[0] # type: ignore
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
                criterion_id = cur.fetchone()[0] # type: ignore
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
            SELECT e.entity_name, e.entity_url, t.tag_value AS summary
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
            import urllib.parse
            results = [{"name": row[0], "url": (row[1] if ('http:' in row[1] or 'https:' in row[1] or 'file:' in row[1]) else 'file://' + urllib.parse.quote(row[1])), "summary": row[2]} for row in results]
        except Exception as e:
            logging.error(f"Error getting entities with summaries: {e}")
            self.conn.rollback()
            # throw the exception again
            raise e
             
        return results
    
    def get_entity_by_url(self, url: str) -> Optional[int]:
        """
        Return the entity ID for which the entity_url matches the given URL.

        Args:
            url (str): The URL to search for.

        Returns:
            Optional[int]: The matching entity ID, or None if not found.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_url = %s LIMIT 1;", (url,))
                result = cur.fetchone()
                if result:
                    return result[0]
                return None
        except Exception as e:
            logging.error(f"Error fetching entity by URL: {e}")
            self.conn.rollback()
            return None
    
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
            k : The number of results to return.
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
        
    def link_entity_to_document(self, entity_id: int, indexed_url: str, indexed_path: str, indexed_type: str = 'pdf', indexed_json: Any = None): 
        """
        Link an entity to a document in the database.

        Args:
            entity_id : The ID of the entity to link.
            indexed_url (str): The URL of the document.
            indexed_path (str): The path of the document.
        """
        try:
            indexed_embed = ''
            if indexed_json:
                indexed_embed = self.generate_embedding(indexed_json['summary'])
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
            entity_id : The entity ID to associate with the table.

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
            return 0
            # throw the exception again
            # raise e
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
            task_id : The ID of the task to delete.
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
        
    def cache_page(self, url: str, text: str):
        """
        Cache a page's contents in the crawl_cache table with a SHA-256 hash and timestamp.

        Args:
            url (str): The URL of the page.
            text (str): The text contents of the page.
        """
        try:
            text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            timestamp = datetime.utcnow()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO crawl_cache (url, content, digest, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE
                    SET content = EXCLUDED.content,
                        digest = EXCLUDED.digest,
                        created_at = EXCLUDED.created_at;
                    """,
                    (url, text, text_hash, timestamp)
                )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error caching page: {e}")
            self.conn.rollback()
            raise e
        
    def cache_page_and_results(self, url: str, text: str, results: str):
        """
        Cache a page's contents and results in the crawl_cache table with a SHA-256 hash, timestamp, and extracted_json.

        Args:
            url (str): The URL of the page.
            text (str): The text contents of the page.
            results (str): The results string to store in extracted_json (should be JSON-serializable).
        """
        try:
            text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            timestamp = datetime.utcnow()
            # Try to parse results as JSON, otherwise store as string
            try:
                extracted_json = json.loads(results)
            except Exception:
                extracted_json = results
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO crawl_cache (url, content, digest, created_at, extracted_json)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE
                    SET content = EXCLUDED.content,
                        digest = EXCLUDED.digest,
                        created_at = EXCLUDED.created_at,
                        extracted_json = EXCLUDED.extracted_json;
                    """,
                    (url, text, text_hash, timestamp, json.dumps(extracted_json))
                )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error caching page and results: {e}")
            self.conn.rollback()
            raise e
        
    def is_page_in_cache(self, url: str, text: str) -> bool:
        """
        Check if the given URL and text content are already cached with the same hash.

        Args:
            url (str): The URL of the page.
            text (str): The text contents of the page.

        Returns:
            bool: True if the cached content matches, False otherwise.
        """
        try:
            text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM crawl_cache WHERE digest = %s and extracted_json is not null;",
                    (text_hash,)
                )
                result = cur.fetchone()
                if result:
                    return True
            return False
        except Exception as e:
            logging.error(f"Error checking page in cache: {e}")
            self.conn.rollback()
            return False
        

    def is_recently_cached(self, url: str) -> bool:
        """
        Check if the given URL is cached with a created_at timestamp within the last 1 hour.

        Args:
            url (str): The URL of the page.

        Returns:
            bool: True if the URL was cached within the last hour, False otherwise.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM crawl_cache
                    WHERE url = %s AND created_at >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour'
                    LIMIT 1;
                    """,
                    (url,)
                )
                result = cur.fetchone()
                return result is not None
        except Exception as e:
            logging.error(f"Error checking if URL is recently cached: {e}")
            self.conn.rollback()
            return False
        
    def get_cached_output(self, url: str, text: str) -> Optional[dict]:
        """
        Check if the given URL and text content are already cached with the same hash.
        If so, return the extracted_json as a dictionary object.

        Args:
            url (str): The URL of the page.
            text (str): The text contents of the page.

        Returns:
            Optional[dict]: The extracted_json field as a dictionary if present and matching, else None.
        """
        try:
            text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT extracted_json FROM crawl_cache WHERE url = %s AND digest = %s;",
                    (url, text_hash)
                )
                result = cur.fetchone()
                if result and result[0]:
                    # If extracted_json is not None, parse and return as dict
                    if isinstance(result[0], dict):
                        return result[0]
                    try:
                        return json.loads(result[0])
                    except Exception:
                        return None
            return None
        except Exception as e:
            logging.error(f"Error getting cached output: {e}")
            self.conn.rollback()
            return None
        
    def get_entity_ids_by_url(self, url: str, type: str = None) -> List[int]: # type: ignore
        """
        Return a list of entity IDs for which the entity_url matches the given URL.

        Args:
            url (str): The URL to search for.
            type (Optional[str]): The type of entity to filter by (e.g., 'paper', 'author'). Defaults to None.

        Returns:
            List[int]: A list of matching entity IDs.
        """
        try:
            with self.conn.cursor() as cur:
                if type:
                    cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_url = %s AND entity_type = %s;", (url, type))
                else:
                    cur.execute(f"SELECT entity_id FROM {self.schema}.entities WHERE entity_url = %s;", (url,))
                entity_ids = [row[0] for row in cur.fetchall()]
            return entity_ids
        except Exception as e:
            logging.error(f"Error fetching entity IDs by URL: {e}")
            self.conn.rollback()
            return []
        
    def is_paper_in_db(self, url: str) -> bool:
        """
        Check if the given URL exists in the database.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL exists, False otherwise.
        """
        entity_ids = self.get_entity_ids_by_url(url, 'paper')
        return len(entity_ids) > 0
    
    def re_embed_all_documents(self):
        """
        Recompute Gemini embeddings for all papers in the entities table.
        This updates the gem_embed field based on the entity_detail using gemini_doc_embedding from llms.py.
        Processes papers in batches of 250 for efficiency.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id, entity_detail FROM {self.schema}.entities WHERE entity_type = 'paper' AND gem_embed IS NULL;")
                papers = cur.fetchall()
                batch_size = 250
                total = len(papers)
                for batch_start in range(0, total, batch_size):
                    batch = papers[batch_start:batch_start + batch_size]
                    entity_ids = [entity_id for entity_id, entity_detail in batch if entity_detail]
                    details = [entity_detail for entity_id, entity_detail in batch if entity_detail]
                    if details:
                        embeddings = gemini_doc_embedding(details)
                        for idx, entity_id in enumerate(entity_ids):
                            embedding = embeddings[idx]
                            cur.execute(
                                f"UPDATE {self.schema}.entities SET gem_embed = %s WHERE entity_id = %s;",
                                (embedding, entity_id)
                            )
                    self.conn.commit()
                    logging.info(f"Re-embedded {min(batch_start + batch_size, total)} of {total} papers with Gemini embeddings.")
                    time.sleep(2)
            logging.info(f"Re-embedded a total of {total} papers with Gemini embeddings.")
        except Exception as e:
            logging.error(f"Error re-embedding papers with Gemini: {e}")
            self.conn.rollback()
            raise e
        
    def re_embed_all_tags(self):
        """
        Recompute Gemini embeddings for all tags in the entity_tags table.
        This updates the gem_embed field based on the tag_value using gemini_doc_embedding from llms.py.
        Processes tags in batches of 250 for efficiency.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id, tag_name, tag_value FROM {self.schema}.entity_tags WHERE gem_embed IS NULL;")
                tags = cur.fetchall()
                batch_size = 250
                total = len(tags)
                for batch_start in range(0, total, batch_size):
                    batch = tags[batch_start:batch_start + batch_size]
                    tag_values = [tag_value for _, _, tag_value in batch if tag_value]
                    embeddings = gemini_doc_embedding(tag_values) if tag_values else []
                    embed_idx = 0
                    for entity_id, tag_name, tag_value in batch:
                        if tag_value:
                            embedding = embeddings[embed_idx]
                            embed_idx += 1
                            cur.execute(
                                f"UPDATE {self.schema}.entity_tags SET gem_embed = %s WHERE entity_id = %s AND tag_name = %s;",
                                (embedding, entity_id, tag_name)
                            )
                    self.conn.commit()
                    logging.info(f"Re-embedded {min(batch_start + batch_size, total)} of {total} tags with Gemini embeddings.")
                    time.sleep(2)
        except Exception as e:
            logging.error(f"Error re-embedding tags with Gemini: {e}")
            self.conn.rollback()
            raise e
    
    def recompute_all_entity_embeddings(self):
        """
        Recompute embeddings for all entities in the database and update the entity_embed field.
        """
        try:
            # Tags
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id, tag_name, tag_value FROM {self.schema}.entity_tags;")
                tags = cur.fetchall()
                for entity_id, tag_name, tag_value in tags:
                    if tag_value:
                        tag_embedding = self.generate_embedding(tag_value)
                        cur.execute(f"UPDATE {self.schema}.entity_tags SET tag_embed = %s WHERE entity_id = %s AND tag_name = %s;", (tag_embedding, entity_id, tag_name))
                        
            # For a paper, recompute the entity_embed by finding the linked entity_tag and copying its summary. If one doesn't exist, take the filename at the end of the URL
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id, entity_url FROM {self.schema}.entities WHERE entity_type = 'paper';")
                papers = cur.fetchall()
                for entity_id, entity_url in papers:
                    # Try to get the summary tag
                    cur.execute(f"SELECT tag_value FROM {self.schema}.entity_tags WHERE entity_id = %s AND tag_name = 'summary' ORDER BY entity_tag_instance ASC LIMIT 1;", (entity_id,))
                    summary_row = cur.fetchone()
                    if summary_row and summary_row[0]:
                        embedding = self.generate_embedding(summary_row[0])
                    else:
                        # Fallback: use filename at end of URL
                        filename = entity_url.split('/')[-1] if entity_url else ''
                        embedding = self.generate_embedding(filename)
                    cur.execute(f"UPDATE {self.schema}.entities SET entity_embed = %s WHERE entity_id = %s;", (embedding, entity_id))
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT entity_id, COALESCE(entity_name, entity_detail) FROM {self.schema}.entities;")
                entities = cur.fetchall()
                for entity_id, content in entities:
                    if content:
                        embedding = self.generate_embedding(content)
                        cur.execute(f"UPDATE {self.schema}.entities SET entity_embed = %s WHERE entity_id = %s;", (embedding, entity_id))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error recomputing entity embeddings: {e}")
            self.conn.rollback()
            raise e

    def save_user_profile(self, email: str, profile_data: dict, profile_context: Optional[str] = None) -> int:
        """
        Save a textual user profile for the user identified by email into user_profiles.
        The text is stored in profile_data as JSON: { "descriptor": "<profile_data>" }.
        
        Args:
            email: User's email (must exist in users table).
            profile_text: The textual profile to store.
            profile_context: Optional context string.

        Returns:
            int: The newly created profile_id.
        """
        try:
            with self.conn.cursor() as cur:
                # Lookup user_id by email
                cur.execute("SELECT user_id FROM users WHERE email = %s;", (email,))
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"User with email {email} not found")
                user_id = row[0]

                # Insert profile row
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile_data, profile_context)
                    VALUES (%s, %s, %s)
                    RETURNING profile_id;
                    """,
                    (user_id, json.dumps({"descriptor": profile_data}), profile_context)
                )
                profile_id = cur.fetchone()[0]  # type: ignore

            self.conn.commit()
            return profile_id
        except Exception as e:
            logging.error(f"Error saving user profile text: {e}")
            self.conn.rollback()
            raise

    def get_user_profile(self, email: str) -> Optional[dict]:
        """
        Retrieve the user's profile descriptor from user_profiles by email.

        Args:
            email: User's email.

        Returns:
            Optional[dict]: The profile descriptor dictionary, or None if not found.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE email = %s;", (email,))
                row = cur.fetchone()
                if not row:
                    return None
                user_id = row[0]
                cur.execute("SELECT profile_data, scholar_id FROM user_profiles WHERE user_id = %s ORDER BY profile_id DESC LIMIT 1;", (user_id,))
                profile_row = cur.fetchone()
                if profile_row and profile_row[0]:
                    data = profile_row[0]
                    ret = data.get("descriptor")
                    ret['scholar_id'] = profile_row[1]
                    
                    return ret
        except Exception as e:
            logging.error(f"Error fetching user profile: {e}")
            self.conn.rollback()
            return None
        
    def get_author_by_scholar_id(self, scholar_id: str) -> Optional[dict]:
        """
        Find the author entity matching a Google Scholar ID and return the person's Scholar JSON record.

        Args:
            scholar_id (str): The Google Scholar ID to search for.
            name (Optional[str]): Optionally filter by name.
            organization (Optional[str]): Optionally filter by organization.

        Returns:
            Optional[dict]: The author's Scholar JSON record, or None if not found.
        """
        try:
            # Build the Scholar profile URL
            scholar_url = f"https://scholar.google.com/citations?user={scholar_id}"
            query = f"SELECT entity_json FROM {self.schema}.entities WHERE entity_type = 'google_scholar_profile' AND entity_url = %s"
            params = [scholar_url]

            with self.conn.cursor() as cur:
                cur.execute(query, tuple(params))
                row = cur.fetchone()
                if row and row[0]:
                    # entity_json is stored as JSON string
                    try:
                        return row[0]
                    except Exception:
                        return row[0]
            return None
        except Exception as e:
            logging.error(f"Error fetching author by Scholar ID: {e}")
            self.conn.rollback()
            return None

    def get_system_profile(self) -> Optional[dict]:
        """
        Retrieve the system profile from user_profiles where user_id is NULL.

        Returns:
            Optional[dict]: The system profile descriptor dictionary, or None if not found.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT profile_data, profile_context FROM user_profiles WHERE user_id IS NULL ORDER BY profile_id DESC LIMIT 1;")
                profile_row = cur.fetchone()
                if profile_row and profile_row[1]:
                    data = profile_row[0]
                    ret = data.get("descriptor") if isinstance(data, dict) else data
                    # Optionally add context if present
                    if isinstance(ret, dict):
                        ret['profile_context'] = profile_row[1]
                    elif ret is None:
                        ret = {'profile_context': profile_row[1]}
                    return ret
        except Exception as e:
            logging.error(f"Error fetching system profile: {e}")
            self.conn.rollback()
            return None

    def set_system_profile(self, profile_data: dict, profile_context: Optional[str] = None) -> int:
        """
        Save the system profile into user_profiles with user_id as NULL.

        Args:
            profile_data: The profile descriptor dictionary.
            profile_context: Optional context string.

        Returns:
            int: The newly created profile_id.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile_data, profile_context)
                    VALUES (NULL, %s, %s)
                    RETURNING profile_id;
                    """,
                    (json.dumps({"descriptor": profile_data}), profile_context)
                )
                profile_id = cur.fetchone()[0]  # type: ignore
            self.conn.commit()
            return profile_id
        except Exception as e:
            logging.error(f"Error saving system profile: {e}")
            self.conn.rollback()
            raise
                
                
    def set_selected_project_for_user(self, user_id: int, project_id: int) -> None:
        """
        Set the selected project id into user_profiles.profile_data.descriptor.selected_project_id
        for the latest profile row for this user, creating a new row if none exists.
        """
        try:
            with self.conn.cursor() as cur:
                # Ensure the latest row exists; if not, create one with empty descriptor
                cur.execute("SELECT profile_id, profile_data FROM user_profiles WHERE user_id = %s ORDER BY profile_id DESC LIMIT 1;", (user_id,))
                row = cur.fetchone()

                if row:
                    # Update JSON using jsonb_set, keeping other data intact
                    cur.execute(
                        """
                        UPDATE user_profiles
                        SET profile_data = jsonb_set(profile_data::jsonb, '{descriptor,selected_project_id}', to_jsonb(%s::int), true)::json
                        WHERE profile_id = %s;
                        """,
                        (project_id, row[0])
                    )
                else:
                    # Insert minimal descriptor with selected_project_id
                    cur.execute(
                        """
                        INSERT INTO user_profiles (user_id, profile_data)
                        VALUES (%s, %s)
                        """,
                        (user_id, json.dumps({"descriptor": {"selected_project_id": project_id}}))
                    )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error setting selected project: {e}")
            self.conn.rollback()
            raise

    def get_selected_project_for_user(self, user_id: int) -> Optional[int]:
        """
        Read selected_project_id from the latest profile_data.descriptor.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT profile_data FROM user_profiles WHERE user_id = %s ORDER BY profile_id DESC LIMIT 1;",
                    (user_id,)
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    return None
                data = row[0]
                # data is JSON with {"descriptor": {...}}
                descriptor = data.get("descriptor") if isinstance(data, dict) else None
                if descriptor and isinstance(descriptor, dict):
                    sel = descriptor.get("selected_project_id")
                    if isinstance(sel, int):
                        return sel
            return None
        except Exception as e:
            logging.error(f"Error reading selected project: {e}")
            self.conn.rollback()
            return None

    def get_user_and_project_ids(self, email: str, project_name: Optional[str] = None) -> Optional[Tuple[int, int]]:
        """Retrieve the user ID and project ID; prefer the selected project in profile_data if present,
        otherwise choose the latest (highest project_id)."""
        user_id = self.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
        if user_id is None or user_id == 0:
            raise ValueError("User not found")

        # If caller names a project, try to find it for this user
        if project_name is not None and project_name.strip() != '':
            project_id_rows = self.exec_sql(
                "SELECT p.project_id FROM projects p JOIN user_projects up ON p.project_id = up.project_id "
                "WHERE up.user_id = %s AND p.project_name = %s ORDER BY p.project_id DESC LIMIT 1;",
                (user_id, project_name)
            )
        else:
            # First try the selected project from profile
            selected = self.get_selected_project_for_user(user_id)
            if selected:
                # Verify the user has access to that project
                rows = self.exec_sql(
                    "SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s;",
                    (user_id, selected)
                )
                if rows:
                    return (user_id, selected)
            # Fallback: latest project by id for this user
            project_id_rows = self.exec_sql(
                "SELECT project_id FROM user_projects WHERE user_id = %s ORDER BY project_id DESC LIMIT 1;",
                (user_id,)
            )

        if not project_id_rows:
            # Create a new project and associate it with the user
            new_project_id_rows = self.exec_sql(
                "INSERT INTO projects (project_name, project_description, created_at) VALUES (%s, %s, %s) RETURNING project_id;",
                (project_name or "New Project", "New project created", datetime.now())
            )
            self.commit()
            new_project_id = new_project_id_rows[0][0]
            self.execute(
                "INSERT INTO user_projects (user_id, project_id) VALUES (%s, %s);",
                (user_id, new_project_id)
            )
            self.commit()
            # Persist selection in profile
            self.set_selected_project_for_user(user_id, new_project_id)
            return (user_id, new_project_id)

        project_id = project_id_rows[0][0]
        # Persist selection if not already set
        try:
            if not self.get_selected_project_for_user(user_id):
                self.set_selected_project_for_user(user_id, project_id)
        except Exception:
            pass
        return (user_id, project_id)


    def add_user_history(self, user_id: int, project_id: int, prompt: str, response: str, description: Optional[str] = None, task_id: Optional[int] = None):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO user_history (user_id, project_id, task_id, predicted_task_description, prompt, response) VALUES (%s, %s, %s, %s, %s, %s);",
                    (user_id, project_id, task_id, description, prompt, response)
                )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error saving user history: {e}")
            self.conn.rollback()
            raise

    def get_user_history(self, user_id: int, project_id: int,task_id: Optional[int] = None, limit: int = 20) -> list:
        try:
            with self.conn.cursor() as cur:
                if task_id:
                    cur.execute(
                        "SELECT prompt, response, predicted_task_description FROM user_history WHERE user_id = %s AND project_id = %s AND task_id = %s ORDER BY created_at DESC LIMIT %s;",
                        (user_id, project_id, task_id, limit)
                    )
                else:
                    cur.execute(
                        "SELECT prompt, response, predicted_task_description FROM user_history WHERE user_id = %s AND project_id = %s ORDER BY created_at DESC LIMIT %s;",
                        (user_id, project_id, limit)
                    )
                return cur.fetchall()
        except Exception as e:
            logging.error(f"Error fetching user history: {e}")
            self.conn.rollback()
            return []        
        
    def update_user_profile(self, email: str, profile: dict):
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE email = %s;", (email,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("User not found")
                user_id = row[0]
                cur.execute("""
                    UPDATE user_profiles
                    SET biosketch = %s, research_areas = %s, projects = %s, publications = %s, profile = %s 
                    WHERE user_id = %s;
                """, (
                    profile.get("biosketch"),
                    profile.get("expertise"),
                    profile.get("projects"),
                    profile.get("publications"),
                    profile,
                    user_id
                ))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error updating user profile: {e}")
            self.conn.rollback()
            raise

    def get_user_projects(self, user_id: int):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT p.project_id, p.project_name, p.project_description
                    FROM user_projects up
                    JOIN projects p ON up.project_id = p.project_id
                    WHERE up.user_id = %s;
                """, (user_id,))
                return [{"id": r[0], "name": r[1], "description": r[2]} for r in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error fetching user projects: {e}")
            self.conn.rollback()
            return []

    def search_projects(self, search: str):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT project_id, project_name, project_description
                    FROM projects
                    WHERE project_name ILIKE %s OR project_description ILIKE %s
                    LIMIT 20;
                """, (f"%{search}%", f"%{search}%"))
                return [{"id": r[0], "name": r[1], "description": r[2]} for r in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error searching projects: {e}")
            self.conn.rollback()
            return []

    def create_project(self, name: str, description: str, user_id: int):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO projects (project_name, project_description, created_at)
                    VALUES (%s, %s, NOW()) RETURNING project_id;
                """, (name, description))
                project_id = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO user_projects (user_id, project_id) VALUES (%s, %s);
                """, (user_id, project_id))
            self.conn.commit()
            return project_id
        except Exception as e:
            logging.error(f"Error creating project: {e}")
            self.conn.rollback()
            raise

    def create_project_task(self, project_id: int, name: str, description: str, schema: str, task_context: Optional[dict] = None) -> int:
        """
        Create a new task for a given project.

        Args:
            project_id (int): The ID of the project.
            name (str): The name of the task.
            description (str): A description of the task.
            schema (str): The schema description for the task.
            task_context (Optional[dict]): Optional JSON-serializable context for the task.

        Returns:
            int: The ID of the newly created task.
        """
        try:
            with self.conn.cursor() as cur:
                embedding = self.generate_embedding(description)
                cur.execute(
                    """
                    INSERT INTO project_tasks (project_id, task_name, task_description, task_schema, task_description_embed, task_context)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING task_id;
                    """,
                    (project_id, name, description, schema, embedding, json.dumps(task_context) if task_context else None)
                )
                task_id = cur.fetchone()[0]
            self.conn.commit()
            return task_id
        except Exception as e:
            logging.error(f"Error creating project task: {e}")
            self.conn.rollback()
            raise

    def link_entity_to_task(self, task_id: int, entity_id: int, feedback_rating: float):
        """
        Link an entity to a task with a feedback rating.

        Args:
            task_id (int): The ID of the task.
            entity_id (int): The ID of the entity.
            feedback_rating (float): The rating for the entity's relevance to the task.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO task_entities (task_id, entity_id, feedback_rating)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (task_id, entity_id) DO UPDATE SET feedback_rating = EXCLUDED.feedback_rating;
                    """,
                    (task_id, entity_id, feedback_rating)
                )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error linking entity to task: {e}")
            self.conn.rollback()
            raise

    def get_tasks_for_project(self, project_id: int) -> List[dict]:
        """
        Retrieve all tasks for a given project.

        Args:
            project_id (int): The ID of the project.

        Returns:
            List[dict]: A list of tasks.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT task_id, task_name, task_description, task_schema FROM project_tasks WHERE project_id = %s ORDER BY task_id;",
                    (project_id,)
                )
                return [{"id": r[0], "name": r[1], "description": r[2], "schema": r[3]} for r in cur.fetchall()]
        except Exception as e:
            logging.error(f"Error fetching tasks for project: {e}")
            return []

    def find_most_related_task_in_project(self, project_id: int, description: str) -> Optional[dict]:
        """
        Find the most related task in a project based on a description.

        Args:
            project_id (int): The ID of the project.
            description (str): The description to match against.

        Returns:
            Optional[dict]: The most related task, or None if not found.
        """
        try:
            with self.conn.cursor() as cur:
                embedding = self.generate_embedding(description)
                cur.execute(
                    """
                    SELECT task_id, task_name, task_description, task_schema
                    FROM project_tasks
                    WHERE project_id = %s
                    ORDER BY task_description_embed <-> %s::vector
                    LIMIT 1;
                    """,
                    (project_id, embedding)
                )
                task = cur.fetchone()
                if task:
                    return {"id": task[0], "name": task[1], "description": task[2], "schema": task[3]}
            return None
        except Exception as e:
            logging.error(f"Error finding related task in project: {e}")
            return None

    def get_entities_for_task(self, task_id: int) -> List[dict]:
        """
        Retrieve all entities for a task, ordered by feedback rating.

        Args:
            task_id (int): The ID of the task.

        Returns:
            List[dict]: A list of entities with their details and ratings.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.entity_id, e.entity_type, e.entity_name, e.entity_detail, e.entity_url, te.feedback_rating
                    FROM entities e
                    JOIN task_entities te ON e.entity_id = te.entity_id
                    WHERE te.task_id = %s
                    ORDER BY te.feedback_rating DESC;
                    """,
                    (task_id,)
                )
                return [{"id": r[0], "type": r[1], "name": r[2], "detail": r[3], "url": r[4], "rating": r[5]} for r in cur.fetchall()]
                
        except Exception as e:
            logging.error(f"Error fetching entities for task: {e}")
            return []

    def find_most_related_task_for_user(self, user_id: int, description: str) -> Optional[dict]:
        """
        Find the most similar task for a user across all their projects.

        Args:
            user_id (int): The ID of the user.
            description (str): The description to match against.

        Returns:
            Optional[dict]: The most related task, or None if not found.
        """
        try:
            with self.conn.cursor() as cur:
                embedding = self.generate_embedding(description)
                cur.execute(
                    """
                    SELECT pt.task_id, pt.task_name, pt.task_description, pt.task_schema
                    FROM project_tasks pt
                    JOIN user_projects up ON pt.project_id = up.project_id
                    WHERE up.user_id = %s
                    ORDER BY pt.task_description_embed <-> %s::vector
                    LIMIT 1;
                    """,
                    (user_id, embedding)
                )
                task = cur.fetchone()
                if task:
                    return {"id": task[0], "name": task[1], "description": task[2], "schema": task[3]}
            return None
        except Exception as e:
            logging.error(f"Error finding related task for user: {e}")
            return None

    def create_task_dependency(self, source_task_id: int, dependent_task_id: int, relationship_description: str, data_schema: str, data_flow: str):
        """
        Create a dependency between two tasks.

        Args:
            source_task_id (int): The ID of the source task (the one that must be completed first).
            dependent_task_id (int): The ID of the dependent task.
            relationship_description (str): A description of the dependency.
            data_schema (str): The schema of the data passed between tasks.
            data_flow (str): The type of data flow (e.g., 'automatic').
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO task_dependencies (source_task_id, dependent_task_id, relationship_description, data_schema, data_flow)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (source_task_id, dependent_task_id) DO UPDATE SET
                        relationship_description = EXCLUDED.relationship_description,
                        data_schema = EXCLUDED.data_schema,
                        data_flow = EXCLUDED.data_flow;
                    """,
                    (source_task_id, dependent_task_id, relationship_description, data_schema, data_flow)
                )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error creating task dependency: {e}")
            self.conn.rollback()
            raise

    def get_task_dependencies(self, task_id: int) -> List[dict]:
        """
        Retrieve all tasks that a given task depends on.

        Args:
            task_id (int): The ID of the dependent task.

        Returns:
            List[dict]: A list of source tasks.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pt.task_id, pt.task_name, pt.task_description, pt.task_schema, td.data_flow
                    FROM project_tasks pt
                    JOIN task_dependencies td ON pt.task_id = td.source_task_id
                    WHERE td.dependent_task_id = %s;
                    """,
                    (task_id,)
                )
                return [{"id": r[0], "name": r[1], "description": r[2], "schema": r[3], "dataflow": r[4]} for r in cur.fetchall()]
                
        except Exception as e:
            logging.error(f"Error fetching task dependencies: {e}")
            self.conn.rollback()
            return []

    def get_all_dependencies_for_project(self, project_id: int) -> List[dict]:
        """
        Retrieve all task dependencies within a given project.

        Args:
            project_id (int): The ID of the project.

        Returns:
            List[dict]: A list of dependency relationships.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT td.source_task_id, td.dependent_task_id, td.relationship_description, td.data_schema, td.data_flow
                    FROM task_dependencies td
                    JOIN project_tasks pt_source ON td.source_task_id = pt_source.task_id
                    JOIN project_tasks pt_dependent ON td.dependent_task_id = pt_dependent.task_id
                    WHERE pt_source.project_id = %s AND pt_dependent.project_id = %s;
                    """,
                    (project_id, project_id)
                )
                return [
                    {
                        "source": r[0],
                        "target": r[1],
                        "relationship_description": r[2],
                        "data_schema": r[3],
                        "data_flow": r[4]
                    } for r in cur.fetchall()
                ]
        except Exception as e:
            logging.error(f"Error fetching all project dependencies: {e}")
            return []


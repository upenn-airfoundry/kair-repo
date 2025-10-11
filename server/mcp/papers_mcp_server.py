import os
import io
import sys
import json
import tempfile
import logging
import requests
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from fastmcp import FastMCP

# Make project root importable for GraphAccessor
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.graph_db import GraphAccessor

# NEW: use google-generativeai directly (no LangChain here)
import google.generativeai as genai

# Optional GROBID
GROBID_SERVER = None#os.getenv("GROBID_SERVER", "http://localhost:8070")
try:
    if GROBID_SERVER:
        from grobid_client.grobid_client import GrobidClient  # type: ignore
    else:
        GrobidClient = None  # type: ignore
except Exception:
    GrobidClient = None  # type: ignore

graph_accessor = GraphAccessor()

app = FastMCP(
    name="papers-indexer",
    version="0.1.1"
)

class OutputDef(BaseModel):
    name: str = Field(..., description="Desired output name (used as tag_name).")
    goal: str = Field(..., description="Goal or prompt describing how to extract this output.")
    type: str = Field(..., description="Expected type: string|number|boolean|date|json.")
    description: Optional[str] = Field(None, description="Optional description.")

class IndexRequest(BaseModel):
    urls: List[str] = Field(..., description="List of PDF URLs to index.")
    outputs: List[OutputDef] = Field(..., description="List of desired outputs with goals and types.")

class IndexResult(BaseModel):
    results: Dict[str, Dict[str, Any]] = Field(
        ..., description="Per-URL mapping of desired output name -> extracted value."
    )

def _download_pdf(url: str) -> bytes:
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    return r.content

def _process_with_grobid(pdf_path: str, out_dir: str) -> Optional[str]:
    if GrobidClient is None:
        return None
    try:
        client = GrobidClient(grobid_server=GROBID_SERVER)
        client.process(
            service="processFulltextDocument",
            input_path=os.path.dirname(pdf_path),
            output=out_dir,
            n=1,
            force=True
        )
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        for fn in os.listdir(out_dir):
            if fn.startswith(base) and fn.endswith(".tei.xml"):
                return os.path.join(out_dir, fn)
        for fn in os.listdir(out_dir):
            if fn.endswith(".tei.xml"):
                return os.path.join(out_dir, fn)
    except Exception as e:
        logging.warning(f"GROBID processing failed: {e}")
    return None

def _parse_tei(tei_path: str) -> Dict[str, Any]:
    from xml.etree import ElementTree as ET
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    result = {"title": None, "abstract": None, "authors": [], "body_text": None}
    try:
        root = ET.parse(tei_path).getroot()
        title_el = root.find(".//tei:titleStmt/tei:title", ns)
        if title_el is not None:
            result["title"] = " ".join("".join(title_el.itertext()).split()) or None
        abs_el = root.find(".//tei:abstract", ns)
        if abs_el is not None:
            result["abstract"] = " ".join(" ".join(abs_el.itertext()).split())
        body_el = root.find(".//tei:body", ns)
        if body_el is not None:
            result["body_text"] = " ".join(" ".join(body_el.itertext()).split())
        for author_el in root.findall(".//tei:sourceDesc//tei:author", ns):
            pers = author_el.find(".//tei:persName", ns)
            if pers is not None:
                fn = pers.findtext("tei:forename", default="", namespaces=ns) or ""
                sn = pers.findtext("tei:surname", default="", namespaces=ns) or ""
                full = " ".join([fn.strip(), sn.strip()]).strip()
                if full:
                    result["authors"].append(full)
                    continue
            txt = " ".join(" ".join(author_el.itertext()).split())
            if txt:
                result["authors"].append(txt)
    except Exception as e:
        logging.warning(f"Failed to parse TEI: {e}")
    return result

def _heuristic_extract(pdf_bytes: bytes) -> Dict[str, Any]:
    result = {"title": None, "abstract": None, "authors": []}
    try:
        head = pdf_bytes[:8192]
        txt = head.decode("latin-1", errors="ignore")
        if "Abstract" in txt:
            idx = txt.find("Abstract")
            result["abstract"] = " ".join(txt[idx: idx + 1200].split())
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        if lines:
            result["title"] = lines[0][:256]
    except Exception:
        pass
    return result

def _extract_pdf_text(pdf_path: str) -> str:
    try:
        try:
            from pypdf import PdfReader
        except Exception:
            from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        texts: List[str] = []
        for page in getattr(reader, "pages", []):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t:
                texts.append(t)
        return "\n\n".join(texts)
    except Exception as e:
        logging.warning(f"PDF text extraction failed for {pdf_path}: {e}")
        return ""

def _chunk_text(text: str, max_chars: int = 12000, overlap: int = 800) -> List[str]:
    if not text:
        return []
    chunks: List[str] = []
    i, n = 0, len(text)
    while i < n:
        j = min(i + max_chars, n)
        chunks.append(text[i:j])
        if j == n:
            break
        i = max(0, j - overlap)
    return chunks

def _merge_extractions(base: Dict[str, Any], new: Dict[str, Any], outputs: List[OutputDef]) -> Dict[str, Any]:
    type_map = {o.name: (o.type or "string").lower() for o in outputs}
    for k, v in new.items():
        t = type_map.get(k, "string")
        if base.get(k) is None:
            base[k] = v
            continue
        if v is None:
            continue
        if t in ("string", "text"):
            bv = base.get(k)
            if isinstance(v, str) and (not isinstance(bv, str) or len(v) > len(bv or "")):
                base[k] = v
        elif t in ("json", "object", "array"):
            base[k] = v
        # numbers/bools: keep first non-null
    return base

def _get_genai_model():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set for google-generativeai")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

def _llm_extract_outputs(text_chunks: List[str], outputs: List[OutputDef]) -> Dict[str, Any]:
    if not text_chunks:
        return {o.name: None for o in outputs}
    try:
        model = _get_genai_model()
    except Exception as e:
        logging.error(f"GenAI init failed: {e}")
        return {o.name: None for o in outputs}

    outputs_schema = [
        {"name": o.name, "type": o.type, "goal": o.goal, **({"description": o.description} if o.description else {})}
        for o in outputs
    ]
    schema_json = json.dumps(outputs_schema, indent=2)
    accumulator: Dict[str, Any] = {o.name: None for o in outputs}

    instruction = (
        "You extract structured information from scientific papers.\n"
        "Rules:\n"
        "1) Use ONLY the provided text; do not fabricate.\n"
        "2) If an output is not present, set it to null.\n"
        "3) Return ONLY a minified JSON object with keys EXACTLY equal to the output names.\n"
        "Desired outputs schema (JSON array):\n"
        f"{schema_json}\n"
    )

    for chunk in text_chunks:
        try:
            prompt = (
                instruction
                + "\nPaper text chunk:\n```text\n"
                + chunk
                + "\n```\nReturn the JSON now."
            )
            resp = model.generate_content(prompt)
            if not resp or not getattr(resp, "text", None):
                continue
            s = resp.text.strip()
            if s.startswith("```"):
                first_nl = s.find("\n")
                if first_nl != -1:
                    s = s[first_nl + 1:]
                if s.endswith("```"):
                    s = s[:-3]
                s = s.strip()
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                accumulator = _merge_extractions(accumulator, parsed, outputs)
        except Exception as e:
            logging.warning(f"LLM extraction failed on a chunk: {e}")
            continue

    return accumulator

#@app.tool(name="index_papers", description="Index papers and annotate desired outputs.", args_schema=IndexRequest, returns=IndexResult)
@app.tool(name="index_papers", description="Index papers and annotate desired outputs.")
def index_papers(req: IndexRequest) -> IndexResult:
    return index_papers_impl(req)

def index_papers_impl(req: IndexRequest) -> IndexResult:
    results: Dict[str, Dict[str, Any]] = {}

    with tempfile.TemporaryDirectory(prefix="papers_mcp_") as tmpdir:
        out_dir = os.path.join(tmpdir, "tei_xml")
        os.makedirs(out_dir, exist_ok=True)

        for url in req.urls:
            try:
                pdf = _download_pdf(url)
                base = os.path.basename(url).split("?")[0] or "paper"
                if not base.lower().endswith(".pdf"):
                    base += ".pdf"
                pdf_path = os.path.join(tmpdir, base)
                with open(pdf_path, "wb") as f:
                    f.write(pdf)

                title = None
                abstract = None
                authors: List[str] = []

                tei_path = _process_with_grobid(pdf_path, out_dir) if GrobidClient else None
                full_text = ""
                if tei_path:
                    meta = _parse_tei(tei_path)
                    title = meta.get("title") or title
                    abstract = meta.get("abstract") or abstract
                    authors = meta.get("authors") or authors
                    full_text = (meta.get("body_text") or "")
                else:
                    meta2 = _heuristic_extract(pdf)
                    title = meta2.get("title") or title
                    abstract = meta2.get("abstract") or abstract
                    full_text = _extract_pdf_text(pdf_path)

                if not full_text:
                    full_text = _extract_pdf_text(pdf_path)

                meta_json = {"source_url": url, "authors": authors}
                paper_id = _upsert_paper_entity(url, title, abstract, meta_json)

                if abstract:
                    _set_tag(paper_id, "summary", abstract, None, instance=1)
                for i, a in enumerate(authors, start=1):
                    _set_tag(paper_id, "author", a, None, instance=i)

                text_for_extraction = (full_text or abstract or "")[:2_000_000]
                chunks = _chunk_text(text_for_extraction, max_chars=12000, overlap=800)
                extracted = _llm_extract_outputs(chunks, req.outputs)

                for out in req.outputs:
                    val = extracted.get(out.name)
                    _set_tag(
                        paper_id,
                        out.name,
                        "" if val is None else (json.dumps(val) if isinstance(val, (dict, list)) else str(val)),
                        tag_json={"goal": out.goal, "type": out.type, "source": "fulltext" if full_text else "abstract"},
                        instance=1
                    )

                results[url] = extracted
            except Exception as e:
                logging.exception(f"Failed to index {url}")
                results[url] = {o.name: None for o in req.outputs}

    try:
        graph_accessor.commit()
    except Exception:
        logging.warning("DB commit failed; attempting rollback")
        try:
            graph_accessor.rollback()
        except Exception:
            pass

    return IndexResult(results=results)

# DB helpers (unchanged)
def _upsert_paper_entity(url: str, title: Optional[str], abstract: Optional[str], meta_json: Dict[str, Any]) -> int:
    rows = graph_accessor.exec_sql(
        """
        INSERT INTO entities (entity_type, entity_name, entity_detail, entity_url, entity_json)
        VALUES ('paper', %s, %s, %s, %s)
        ON CONFLICT (entity_type, entity_name, entity_url)
        DO UPDATE SET entity_detail = EXCLUDED.entity_detail, entity_json = EXCLUDED.entity_json
        RETURNING entity_id;
        """,
        (title or url, abstract or "", url, json.dumps(meta_json))
    )
    if rows and rows[0] and rows[0][0]:
        return rows[0][0]
    rows = graph_accessor.exec_sql(
        "SELECT entity_id FROM entities WHERE entity_type='paper' AND entity_name=%s AND entity_url=%s;",
        (title or url, url)
    )
    if rows:
        return rows[0][0]
    raise RuntimeError("Failed to upsert paper entity")

def _set_tag(entity_id: int, name: str, value: str, tag_json: Optional[Dict[str, Any]] = None, instance: int = 1) -> None:
    graph_accessor.execute(
        """
        INSERT INTO entity_tags (entity_id, entity_tag_instance, tag_name, tag_value, tag_json)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (entity_id, entity_tag_instance, tag_name)
        DO UPDATE SET tag_value = EXCLUDED.tag_value, tag_json = EXCLUDED.tag_json;
        """,
        (entity_id, instance, name, value, json.dumps(tag_json) if tag_json is not None else None)
    )

if __name__ == "__main__":
    app.run()
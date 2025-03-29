import React, { useState } from "react";
import axios from "axios";

function App() {
  const url2 = "http://localhost:8081";

  const [tagName, setTagName] = useState("");
  const [query, setQuery] = useState("");
  const [k, setK] = useState(10);
  const [entityType, setEntityType] = useState("");
  const [keywords, setKeywords] = useState("");
  const [url, setUrl] = useState("");
  const [comment, setComment] = useState("");
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState("");

  const handleFindRelatedEntitiesByTag = async () => {
    try {
      const response = await axios.get(url2 + "/find_related_entities_by_tag", {
        params: { tag_name: tagName, query, k },
      });
      setResults(response.data.results);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleFindRelatedEntities = async () => {
    try {
      const response = await axios.get(url2 + "/find_related_entities", {
        params: { query, k, entity_type: entityType, keywords: keywords.split(",") },
      });
      setResults(response.data.results);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleAddToCrawlQueue = async () => {
    try {
      const response = await axios.post(url2 + "/add_to_crawl_queue", { url, comment });
      setMessage(response.data.message);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleCrawlPDF = async () => {
    try {
      const response = await axios.post(url2 + "/crawl_pdf");
      setMessage(response.data.message);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleParsePDFsAndIndex = async () => {
    try {
      const response = await axios.post(url2 + "/parse_pdfs_and_index");
      setMessage(response.data.message);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleGetUncrawledEntries = async () => {
    try {
      const response = await axios.get(url2 + "/uncrawled_entries");
      setResults(response.data.uncrawled_entries);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      <h1>Flask Backend Operations</h1>

      <div>
        <h2>Find Related Entities by Tag</h2>
        <input
          type="text"
          placeholder="Tag Name"
          value={tagName}
          onChange={(e) => setTagName(e.target.value)}
        />
        <input
          type="text"
          placeholder="Query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <input
          type="number"
          placeholder="k"
          value={k}
          onChange={(e) => setK(e.target.value)}
        />
        <button onClick={handleFindRelatedEntitiesByTag}>Search</button>
      </div>

      <div>
        <h2>Find Related Entities</h2>
        <input
          type="text"
          placeholder="Query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <input
          type="number"
          placeholder="k"
          value={k}
          onChange={(e) => setK(e.target.value)}
        />
        <input
          type="text"
          placeholder="Entity Type"
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        />
        <input
          type="text"
          placeholder="Keywords (comma-separated)"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
        <button onClick={handleFindRelatedEntities}>Search</button>
      </div>

      <div>
        <h2>Add to Crawl Queue</h2>
        <input
          type="text"
          placeholder="URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <input
          type="text"
          placeholder="Comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <button onClick={handleAddToCrawlQueue}>Add</button>
      </div>

      <div>
        <h2>Crawl PDFs</h2>
        <button onClick={handleCrawlPDF}>Start Crawling</button>
      </div>

      <div>
        <h2>Parse PDFs and Index</h2>
        <button onClick={handleParsePDFsAndIndex}>Parse and Index</button>
      </div>

      <div>
        <h2>Get Uncrawled Entries</h2>
        <button onClick={handleGetUncrawledEntries}>Fetch</button>
      </div>

      <div>
        <h2>Results</h2>
        <pre>{JSON.stringify(results, null, 2)}</pre>
      </div>

      <div>
        <h2>Message</h2>
        <p>{message}</p>
      </div>
    </div>
  );
}

export default App;
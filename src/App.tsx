import React, { useState } from "react";
import { Provider } from "./components/ui/provider.jsx";
import { Heading, Stack, Text } from "@chakra-ui/react"
import { Button, HStack } from "@chakra-ui/react";
import { Box } from "@chakra-ui/react"
import axios from "axios";

import { createSystem, defaultConfig } from "@chakra-ui/react"

export const system = createSystem(defaultConfig, {
  theme: {
    textStyles: {
      h1: {
        // you can also use responsive styles
        fontSize: ['48px', '72px'],
        fontWeight: 'bold',
        lineHeight: '110%',
        letterSpacing: '-2%',
      },
      h2: {
        fontSize: ['36px', '48px'],
        fontWeight: 'semibold',
        lineHeight: '110%',
        letterSpacing: '-1%',
      },
    },
    tokens: {
      fonts: {
        heading: { value: `'Figtree', sans-serif` },
        body: { value: `'Figtree', sans-serif` },
      },
    },
  },
})

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
    <Provider>
    <div style={{ padding: "20px" }}>
      <Heading size="2xl">KAIR Semantic Search</Heading>

        <Heading size="xl">Find Related Entities by Tag</Heading>
        <Box color='gray.50' bgcolor='gray.800' p={4} borderRadius='md'>
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
        <Button onClick={handleFindRelatedEntitiesByTag}>Search</Button>
        </Box>

        <Heading size="xl">Directly Find Related Entities</Heading>
        <Stack align="flex-start">
        <HStack>
        <input
          type="text"
          placeholder="Query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <input
          type="text"
          placeholder="Entity Type"
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        />
        <input
          type="text"
          placeholder="Keywords"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
        <input
          type="number"
          placeholder="k"
          value={k}
          onChange={(e) => setK(e.target.value)}
        />
        <Button onClick={handleFindRelatedEntities}>Search</Button>
        </HStack>
      </Stack>

      <Heading size="xl">Crawler / Indexer Controls</Heading>
      <Stack align="flex-start">
      <Heading size="l">Add an URL to the Crawl Queue</Heading>
        <HStack>
          <input
            type="text"
            placeholder="URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <input
            type="text"
            placeholder="Description"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button onClick={handleAddToCrawlQueue}>Add to Queue</Button>
        </HStack>

        <HStack>
          <Button onClick={handleGetUncrawledEntries}>See Uncrawled</Button>
          <Button onClick={handleCrawlPDF}>Start Crawling</Button>
          <Button onClick={handleParsePDFsAndIndex}>Parse and Index</Button>
        </HStack>
      </Stack>

      <hr/>

      <Heading size="xl">Intermediate (RAG) Results</Heading>
      <Box color='gray.50' bgcolor='gray.800' p={4} borderRadius='md'>
        <pre>{JSON.stringify(results, null, 2)}</pre>
      </Box>

      <div>
        <h2>Message</h2>
        <p>{message}</p>
      </div>
    </div>
    </Provider>
  );
}

export default App;
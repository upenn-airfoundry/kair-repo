import React, { useState } from "react";
import { Provider } from "./components/ui/provider.jsx";
import { useColorModeValue } from "./components/ui/color-mode.jsx";
import { Heading, Stack, Text } from "@chakra-ui/react"
import { Button, HStack, Image } from "@chakra-ui/react";
import { Box } from "@chakra-ui/react"
import axios from "axios";
import { Textarea } from "@chakra-ui/react"

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
  const [prompt, setPrompt] = useState("");
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
        params: { query, k, entity_type: entityType, keywords: keywords },
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

  const handlePrompt = async () => {
    try {
      const response = await axios.post(url2 + "/expand", { prompt });
      setMessage(response.data.data.message);
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  return (
    <Provider>
    <div style={{ padding: "20px" }}>
      <Stack align="flex-start">
      <HStack><Image src="airfoundry.svg" /><Heading size="2xl">KAIR Semantic Search Prototype</Heading></HStack>
      <HStack><Heading size="sm">Copyright (C) 2025 by the Trustees of the University of Pennsylvania</Heading><Image scale="50%" src="logo-NSF.png" /></HStack>
      
      </Stack>
        <Heading size="xl">Pose Your Question:</Heading>
        <Stack>
        <Textarea rows="5" cols="80" width="100" placeholder="Enter your question here..." value={prompt} onChange={(e) => setPrompt(e.target.value)} />  
        <HStack>
        <Button onClick={handlePrompt}>Ask KAIR</Button>
        </HStack>
        </Stack>
        <p>&nbsp;</p>
        <hr/>
        <hr/>

      <Heading size="l">Intermediate (RAG) Results</Heading>
      <Box color='gray.50' bgcolor='gray.800' p={4} borderRadius='md'>
        <Text color="black">
        <pre>{JSON.stringify(results, null, 2)}</pre>
        </Text>
      </Box>

      <Heading size="l">Message</Heading>
      <Box color='gray.50' bgcolor='gray.800' p={4} borderRadius='md'>
        <Text color="black">{message}</Text>
      </Box>

      <p>&nbsp;</p>
      <hr/>
        <Heading size="xl">Low-Level Retrieval</Heading>
        <p>&nbsp;</p>
        <Heading size="l">Retrieve Related Entities by Tag</Heading>
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

        <Heading size="l">Directly Retrieve Entities</Heading>
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

      <p>&nbsp;</p>
      <hr/>

      <Heading size="xl">Crawler / Indexer Controls</Heading>
      <Stack align="flex-start">
      <Heading size="m">Add an URL to the Crawl Queue</Heading>
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
      </div>
      </Provider>

  );
}

export default App;
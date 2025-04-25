import React, { useState, useEffect } from "react";
import { Provider } from "./components/ui/provider.jsx";
import { useColorModeValue } from "./components/ui/color-mode.jsx";
import { Heading, Stack, Text } from "@chakra-ui/react"
import { Button, HStack, Image } from "@chakra-ui/react";
import { Box, Select, Table } from "@chakra-ui/react"
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
  const [assessmentCriteria, setAssessmentCriteria] = useState([]);
  const [selectedCriterion, setSelectedCriterion] = useState("");  
  const [criterionName, setCriterionName] = useState("");
  const [criterionPrompt, setCriterionPrompt] = useState("");
  const [criterionScope, setCriterionScope] = useState("");

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

  const addEnrichment = async () => {
    try {
      const response = await axios.post(url2 + "/add_enrichment", { selectedCriterion });
      setMessage(response.data.message);
    }
    catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  const addCriterion = async () => {
    try {
      var name = criterionName;
      var prompt = criterionPrompt;
      var scope = criterionScope;
      const response = await axios.post(url2 + "/add_assessment_criterion", { name, prompt, scope });
      setMessage(response.data.message);
      setCriterionName("");
      setCriterionPrompt("");
      setCriterionScope("");
      fetchAssessmentCriteria(); // Refresh the criteria list after adding a new one
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };


  const handleCrawlPDF = async () => {
    try {
      const response = await axios.post(url2 + "/crawl_files");
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
  // Fetch assessment criteria from the backend
  const fetchAssessmentCriteria = async () => {
    try {
      const response = await axios.get(url2 + "/get_assessment_criteria");
      console.log(response.data);
      setAssessmentCriteria(response.data.criteria); // Assuming the backend returns { criteria: [...] }
    } catch (error) {
      setMessage(`Error: ${error.response?.data?.error || error.message}`);
    }
  };

  // Handle selection change
  const handleCriterionChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedCriterion(event.target.value);
  };

  // Fetch criteria on component mount
  useEffect(() => {
    fetchAssessmentCriteria();
  }, []);

  return (
    <Provider>
    <div style={{ padding: "20px" }}>
      <Stack align="flex-start">
      <HStack><Image src="airfoundry.svg" /><Heading size="2xl">KAIR Semantic Search Prototype</Heading></HStack>
      <HStack><Heading size="sm">Copyright (C) 2025 by the Trustees of the University of Pennsylvania</Heading><Image scale="50%" src="logo-NSF.png" /></HStack>
      
      </Stack>
        <Heading size="xl">Pose Your Question:</Heading>
        <Stack>
        <Textarea rows={5} cols={80} width={800} placeholder="Enter your question here..." value={prompt} onChange={(e) => setPrompt(e.target.value)} />  
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
        {JSON.stringify(results, null, 2)}
        </Text>
      </Box>

      <Heading size="l">Message</Heading>
      <Box color='gray.50' bgcolor='gray.800' p={4} borderRadius='md'>
        <Text color="black" whiteSpace="pre-line">{message}</Text>
      </Box>

      <p>&nbsp;</p>
      <hr/>
      <Heading size="xl">Assessment Criteria</Heading>
      <p>&nbsp;</p>
      <Stack align="flex-start">
          <table border="2">
            <thead><tr><td><b>Criterion Name</b></td><td><b>Prompt</b></td><td><b>Scope</b></td></tr></thead>
            <tbody>
          {assessmentCriteria.map((x, k) => (<tr key={k}><td>{x.name}</td><td>{x.prompt}</td><td>{x.scope}</td></tr>))}
            <tr><td><b>New: </b><input
          type="text"
          placeholder="Criterion Name"
          value={criterionName}
          onChange={(e) => setCriterionName(e.target.value)}
        /></td><td><input
        type="text"
        placeholder="Prompt"
        value={criterionPrompt}
        onChange={(e) => setCriterionPrompt(e.target.value)}
      /></td><td><input
      type="text"
      placeholder="Scope"
      value={criterionScope}
      onChange={(e) => setCriterionScope(e.target.value)}
    /></td></tr>
            </tbody>
          </table>
        <HStack>
        <Button onClick={addCriterion}>Add New Criterion</Button>
        <Button onClick={addEnrichment}>Enrich</Button></HStack>
      </Stack>

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
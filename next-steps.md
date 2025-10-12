## Planning for mRNA Design

- Load the FastMCP server for Semantic Scholar

Get tool use working from KAIR, to search for papers

Get tool use working from KAIR, to do reverse translation

Get tool use working from KAIR, to call a stub MCP server to get an optimized mRNA

See if we can plan an mRNA design.

Get embeddings server on PARCC.

Port to Qwen3? Run crawler on PARCC.

--

Project is comprised of Tasks

Visualize them as graph, with nodes linked if there is a dataflow.  Each Task node has a Strategy.  Each Strategy consists of Flows and Alternatives.

Clicking on a node shows a set of objects (transitively) related to it.

I need to add an upper pane to the chat page, right above the chat input.  This should be akin to a memory map visualizer

Once we have a successful project completion, we can summarize the steps as a Strategy. Subsequent user tasks are vetted against prior strategies, which can be used RAG-style to improve answer suggestions.

Need to *learn from past related tasks*: source reliability, method reliability, cautions, extra directives or clarifications on prompts, etc.

===

Task [list]
  Description and goals
  Inputs to the task [list]
  Task outputs as fields [list]:
    - Name
    - Datatype
    - Description
    - Importance to task
    - Means of choosing or ranking
    - Potential sources and what they need as input [list]
  Evidence and means of evaluation or assessment
  Criteria for returning to the prior decision
  Does this need the user to clarify?
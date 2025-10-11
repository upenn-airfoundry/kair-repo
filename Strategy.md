Strategy

- Descriptor
- Sub-strategy list
- Prompt
- External tool / MPC
- Usage history



Create account:
- Check if a notable and unambiguous figure, else ask for clarification.
- If not notable, ask for a self description.
- Show biosketch, etc. and allow user to update.
- Allow for educational users and industry users.

GUI for project
- A project resources table has collections, pointers to S3 and GFS resources
- Can these be Entities?
- Each can be annotated with a Usage Context

We need to identify tasks and subtasks
- Infer from LLM -- what am I trying to do, did I switch steps or tasks?
- Did I switch projects?
- Did I backtrack?
- GUI to illustrate

- Do I have a work state Entity?
- It may have a sketch of a target (e.g., schema, etc.)

- To predict the target, we can ask the LLM. If we have related tasks (from the user etc.) we can fetch, feed in a single prompt to the LLM to help it.
- The user can edit the suggested schema and provide potential partial answers.

- Now given the target schema, we can propose multi-step plans.

- We need to register MCP tools to get connections to other resources.
- Paper --> NCBI info, protein --> gene, protein --> mRNA, mRNA --> BayesOpt, etc.

We need a context manager, which keeps the context window from going crazy.
It works on transitive closure based on the task at hand, and the future downstream tasks.



Task-reflective learning
========================

At each query:
- Did I learn something new --> pending item
- What is my goal, what should my result look like?

Periodic:
- Re-interpret the context of my objective
- Refine strategy
- Refine individual steps with a clearer definition
- Does any of this subsume what I was doing before, or obsolete it?

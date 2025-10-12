# KAIR, So Far

* Data-driven -- enrichment and associations to add features. Submission to CIDR.
* Model-driven -- training set annotations, Medex, to appear, NeurIPS 2025, with Jones, Maus, Gardner, Yatskar.

* Still crawling + indexing + enriching
* Still need to do dataset linking, provenance. Can we do this at the data level?

Now we can focus on an intermediate part, which is the *workflows*.

# Semantic Data-Driven Workflows

Basic idea: the system has a known number of *states* with likely *transitions* to *next* states and *redo points*.

The user selects a *project* with an *objective*. The user also has a history.

For *goals* and even *states*, we have an open set of *strategies*, which can be populated via CoT but can be refined. Strategies have multiple states and suggested transitions.

Additionally: there may be *general context and memory*.

These are connected to *project datasets*.

DISPLAY:
The system needs to show a summary of what it thinks the *goal*, the *strategy*, and the *state* are. The user can override when these are wrong.

INITIAL:
We collect information about who the user is.  From this, the project, etc., we describe a *likely set of goals*.

IN EACH ITERATION:

When the user asks about something, we decide:
* Is it related to our current state?
* Does it suggest a decision was made and we move to a next state --- or a prior state?
* Does it provide further context as to goals or data?

Each time the system performs an action, the results:

1. Are logged and added to context.
1. If sets of answers / data: Can be added to project data.
1. Are interpreted for significance. We may recompute both context and goals as a result.
1. Are used to predict next and redo steps.
1. Are used to enumerate *additional options* (e.g., as a human).
1. May lead to "follow-ups", e.g., pointers to additional data.

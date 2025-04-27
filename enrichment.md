# Enrichment

The enrichment capabilities are driven by [iterative_enrichment](enrichment/iterative_enrichment.py). The function `process_next_task` is called to pull an item out of the task queue (`get_next_task`), turn it into an enrichment task, and execute it.  By default, the task is removed from the queue.

> TODO: check if we want to extend, continue, or modify the task in the next round.

## Basic Data

- **Entities**

- **Associations** with *support*, *history*

- **Strategy**: a *strategy* is a descriptor of the steps to handle a task.  It could involve chain-of-thought-style breaking down into substeps (and subtasks). It may have a *cost*, as well as a *promise* that gets updated upon execution and a *reliability*.

> TODO: do we want to have n-ary associations?



## Enrichment Operators

The basic core of the enrichment operator set is in [core_ops](enrichment/core_ops.py) and [langchain_ops](enrichment/langchain_ops.py).  There are multiple kinds of operations (each is side-effecting so is not a standard algebra):

- **Data augmentation**: These are of the form $f: question \mapsto subgraph$.
  - An example would be a Semantic Scholar API call to search for an author or a paper, by topic, name, etc.

- **Entity assessment/interpretation**: These are of the form $f: (entity, \phi) \mapsto annotation_f(annotationValue,support)$ or $g: (entity, \phi) \mapsto task$.  $\phi$ defines a *scope* for the candidate entities, such that $\phi(e) > \tau$ for every entity $e$ that we consider.
  - An example of $f$ would be a prompt to ask about the authors of a paper.
  - An example of $g$ would be a data augmentation task to get further information about an author.

- **Association**: These are of the form $X: (e_1, \phi_1, e_2, \phi_2, \theta_{1,2}) \mapsto assoc_X(strength, support)$, where $e_1, e_2$ are entities.  $\phi_1, \phi_2$ are *scope* functions for $e_1, e_2$ which must return a score above threshold $\tau$; $\theta_{1,2}$ is a *plausibility* function for $X$ between $e1$ and $e2$, and must be above threshold $\Tau$.

- **Adjust support**: These are of the form:

  - $s_e: (entity_e, annotation_{f,e}) \mapsto annotation_f(annotationValue',support')$
  - $s_a: (assoc_{X,a:(e1,e2)}) \mapsto assoc_{X,a:(e1,e2)}(strength',support')$

- **Aggregate/generalize**: These are of the form: $\Gamma: entitySet \rightarrow entity$.

- **Paraphrase/transform**:

- **Forget**: Removes an entity or annotation or association.

- **Supersede** Replaces an entity, annotation, or association and creates a history link to its old version.


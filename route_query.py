import json
from typing import List

is_about_paper = [
    "Determine if the question is about searching over academic papers, research articles, or scientific studies.",
    "If it is, respond with 'YES'. If it is not, respond with 'NO'.",
    "Do not provide any additional information or context, just respond with 'YES' or 'NO'."
]

needs_expert = [
    "Determine if the question is about a specialized scientific or technical topic that would require expert knowledge to answer.",
    "If it is, respond with 'YES'. If it is not, respond with 'NO'.",
    "Do not provide any additional information or context, just respond with 'YES' or 'NO'."
]

mrna_vaccine_steps = [
    "Analyze Viral Genome & Predict Antigens: Process the virus's genetic sequence to identify genes coding for surface proteins. Use predictive models to map potential epitopes—the specific sites on those proteins that are most likely to trigger a strong and protective immune response in the target animal.",
    "Design & Optimize mRNA Sequence: Take the scientist's chosen antigen sequence and generate a complete, production-ready mRNA construct. This includes optimizing the genetic code (codons) for efficient expression in the specific animal species and adding the necessary 5' cap, UTRs, and poly(A) tail sequences for stability.",
    "Generate Lab Protocols & SOPs: Create detailed, step-by-step Standard Operating Procedures (SOPs) for the in vitro transcription (IVT) process to synthesize the designed mRNA and for the subsequent purification steps.",
    "Recommend Delivery System Formulations: Scan scientific literature and databases to recommend suitable lipid nanoparticle (LNP) formulations. Provide a comparison of options based on known efficacy and safety in the target species or similar animals.",
    "Design Preclinical Study Protocols: Outline a comprehensive plan for preclinical trials. This includes designing experiments for cell cultures and animal models to test the vaccine's safety, immunogenicity (ability to provoke an immune response), and dosage.",
    "Outline Veterinary Clinical Trial Phases: Draft a structured plan for the required clinical trial phases (I, II, and III) in the target animal population. Define the objectives, number of subjects, safety monitoring procedures, and key efficacy endpoints for each phase."
]

rnai_gene_suppression_steps = [
"Target Selection: The AI agent can scan the entire plant genome and transcriptome (all the expressed genes) to identify the most effective and unique sequence for targeting. It can analyze thousands of potential sites in seconds, flagging regions that are common to all variants of the target gene while being completely absent elsewhere in the genome. This massively reduces the risk of off-target effects.",
"RNAi Trigger Design: This is where AI truly shines. Based on vast datasets from previous experiments, a predictive AI model can: Score potential trigger sequences for their silencing efficiency. Predict and eliminate sequences that are likely to cause off-target effects with a much higher degree of accuracy than a manual search. Optimize the sequence for stability and effective processing by the plant's cellular machinery.",
"Vector Construction: The AI agent can design the optimal DNA vector for the scientist. It can select the best promoter for the specific plant and desired silencing level (e.g., a promoter that is always on or one that only activates in the roots). It can also generate the full DNA sequence for the hairpin construct, ensuring it's optimized for synthesis and cloning.",
"Experimental Analysis: After the experiment, an AI agent can help analyze the results. For example, it can process gene expression data (like from qPCR or RNA-seq) to precisely quantify how much the target gene was silenced and scan the data for any unintended changes in other genes, providing a comprehensive report on the experiment's success and specificity."
]


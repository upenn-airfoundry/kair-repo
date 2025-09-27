from typing import Dict, Optional
import asyncio
from Bio import Entrez
from Bio import SeqIO
from Bio.SeqFeature import FeatureLocation

# MCP server
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("protein-to-mrna")

# Preferred human codon usage mapping (Standard Code, RNA codons)
AA_TO_CODON: Dict[str, str] = {
    "A": "GCC",
    "C": "UGC",
    "D": "GAC",
    "E": "GAG",
    "F": "UUC",
    "G": "GGC",
    "H": "CAC",
    "I": "AUC",
    "K": "AAG",
    "L": "CUG",
    "M": "AUG",
    "N": "AAC",
    "P": "CCG",
    "Q": "CAG",
    "R": "CGC",
    "S": "UCC",
    "T": "ACC",
    "V": "GUG",
    "W": "UGG",
    "Y": "UAC",
    # Stop is handled separately if present: "*": "UAA"
}

def get_full_sequence_record(protein_id: str, email: str):
    """
    Fetches the full GenBank nucleotide record corresponding to a protein ID.

    Args:
        protein_id: The NCBI accession ID for the protein (e.g., "NP_000517.1").
        email: Your email address (required by NCBI for API access).

    Returns:
        A SeqRecord object from BioPython containing the full sequence and annotations,
        or None if not found.
    """
    Entrez.email = email
    
    # 1. Search for the protein ID to get its GI number
    handle = Entrez.esearch(db="protein", term=protein_id)
    record = Entrez.read(handle)
    handle.close()
    if not record["IdList"]:
        print(f"Error: Protein ID {protein_id} not found.")
        return None
    
    # 2. Link from the protein database to the nucleotide database
    protein_gi = record["IdList"][0]
    handle = Entrez.elink(dbfrom="protein", db="nuccore", id=protein_gi)
    record = Entrez.read(handle)
    handle.close()
    if not record[0]["LinkSetDb"]:
        print(f"Error: Could not find a nucleotide link for protein {protein_id}.")
        return None
        
    # 3. Fetch the full GenBank record from the nucleotide database
    nucleotide_id = record[0]["LinkSetDb"][0]["Link"][0]["Id"]
    handle = Entrez.efetch(db="nuccore", id=nucleotide_id, rettype="gb", retmode="text")
    
    # Using SeqIO.read assumes only ONE record is returned, which is typical here.
    # If multiple records could be returned, use SeqIO.parse instead.
    full_record = SeqIO.read(handle, "genbank")
    handle.close()
    
    return full_record

def extract_mrna_components(record: SeqIO.SeqRecord):
    """
    Parses a SeqRecord to extract the 5' UTR, CDS, and 3' UTR sequences.

    Args:
        record: A BioPython SeqRecord object obtained from an NCBI fetch.

    Returns:
        A dictionary containing the sequences for '5_UTR', 'CDS_DNA', 
        'CDS_mRNA', and '3_UTR'. Returns None for features not found.
    """
    # Initialize dictionary to store components
    components = {
        "5_UTR": None,
        "CDS_DNA": None,
        "CDS_mRNA": None,
        "3_UTR": None
    }
    
    # The full sequence is the basis for slicing
    full_sequence = record.seq

    # Find the features in the record
    for feature in record.features:
        # The CDS feature is the most important one
        if feature.type == "CDS":
            # Extract the DNA coding sequence
            cds_location: FeatureLocation = feature.location
            cds_dna_seq = cds_location.extract(full_sequence)
            components["CDS_DNA"] = str(cds_dna_seq)
            
            # Convert CDS to mRNA by replacing Thymine with Uracil
            components["CDS_mRNA"] = str(cds_dna_seq.transcribe())
            
            # Infer UTRs based on the CDS location
            # Note: This is a simplified model. It assumes a single, contiguous CDS
            # and that any sequence before it is the 5' UTR and after it is the 3' UTR.
            cds_start = int(cds_location.start)
            cds_end = int(cds_location.end)

            # 5' UTR is everything before the CDS starts
            if cds_start > 0:
                components["5_UTR"] = str(full_sequence[0:cds_start])
            
            # 3' UTR is everything after the CDS ends
            if cds_end < len(full_sequence):
                components["3_UTR"] = str(full_sequence[cds_end:])
            
            # Once we've found and processed the main CDS, we can stop.
            break 
            
    return components


def _protein_to_mrna(protein_seq: str) -> str:
    """
    Convert a protein sequence to an mRNA CDS using preferred codons.
    Stops at '*' if present. Returns RNA (with U).
    """
    seq = protein_seq.strip().upper().replace("\n", "").replace(" ", "")
    mrna_codons = []
    for aa in seq:
        if aa == "*":
            # stop translation at stop char
            break
        if aa not in AA_TO_CODON:
            raise ValueError(f"Invalid amino acid residue '{aa}' in sequence.")
        mrna_codons.append(AA_TO_CODON[aa])
    return "".join(mrna_codons)

def _coerce_seq_to_str(v: Optional[object]) -> str:
    if v is None:
        return ""
    # Handle Bio.Seq and strings
    try:
        return str(v)
    except Exception:
        return ""

def build_full_mrna_from_protein(protein_sequence: str) -> Dict[str, str]:
    """
    Build full mRNA (5'UTR + CDS + 3'UTR) from a protein sequence.
    Calls extract_mrna_components(record); if UTRs are unavailable,
    falls back to generated CDS for the mRNA body.
    """
    cds_mrna = _protein_to_mrna(protein_sequence)
    record = SeqRecord(Seq(cds_mrna), id="synthetic_mrna", description="Derived from protein sequence")

    try:
        components = extract_mrna_components(record)
    except Exception:
        components = {"5_UTR": None, "CDS_DNA": None, "CDS_mRNA": None, "3_UTR": None}

    five = _coerce_seq_to_str(components.get("5_UTR"))
    cds = _coerce_seq_to_str(components.get("CDS_mRNA")) or cds_mrna
    three = _coerce_seq_to_str(components.get("3_UTR"))

    full = f"{five}{cds}{three}"

    return {
        "five_prime_utr": five,
        "cds_mrna": cds,
        "three_prime_utr": three,
        "full_mrna": full,
    }

@server.tool("protein_to_mrna")
async def protein_to_mrna_tool(protein_sequence: str) -> dict:
    """
    MCP Tool: Takes a protein sequence, returns full mRNA and components.
    """
    result = build_full_mrna_from_protein(protein_sequence)
    return result

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write)


if __name__ == "__main__":
    asyncio.run(main())

# if __name__ == "__main__":
#     # --- CONFIGURATION ---
#     # !! IMPORTANT: Replace with your actual email address !!
#     # NCBI requires this for identification in case of issues.
#     YOUR_EMAIL = "your.email@example.com"
    
#     # Example: Human beta-globin protein
#     PROTEIN_ACCESSION_ID = "NP_000517.1" 
    
#     if YOUR_EMAIL == "your.email@example.com":
#         print("Please update the 'YOUR_EMAIL' variable in the script before running.")
#     else:
#         print(f"🧬 Fetching data for protein: {PROTEIN_ACCESSION_ID}...")
        
#         # 1. Get the full annotated record
#         sequence_record = get_full_sequence_record(PROTEIN_ACCESSION_ID, YOUR_EMAIL)
        
#         if sequence_record:
#             print(f"✅ Found nucleotide record: {sequence_record.id} ({len(sequence_record.seq)} bp)")
            
#             # 2. Parse the record to get the mRNA components
#             mrna_parts = extract_mrna_components(sequence_record)
            
#             print("\n--- mRNA Components ---")
            
#             # Print each component, handling cases where a UTR might not be found
#             five_utr = mrna_parts.get("5_UTR")
#             if five_utr:
#                 print(f"\n🟢 5' UTR ({len(five_utr)} bp):\n{five_utr}\n")
#             else:
#                 print("\n⚪️ 5' UTR: Not found in this record.\n")
                
#             cds_dna = mrna_parts.get("CDS_DNA")
#             if cds_dna:
#                 print(f"🔵 CDS (DNA) ({len(cds_dna)} bp):\n{cds_dna[0:60]}...\n")
            
#             cds_mrna = mrna_parts.get("CDS_mRNA")
#             if cds_mrna:
#                 print(f"🟣 CDS (mRNA) ({len(cds_mrna)} bp):\n{cds_mrna[0:60]}...\n")
                
#             three_utr = mrna_parts.get("3_UTR")
#             if three_utr:
#                 print(f"🔴 3' UTR ({len(three_utr)} bp):\n{three_utr}\n")
#             else:
#                 print("⚪️ 3' UTR: Not found in this record.\n")

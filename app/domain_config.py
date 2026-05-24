"""
Banking domain configuration.

This is THE only file that changes when deploying to a new bank
or adapting the product for a different regulatory vertical.

All UCB-specific knowledge lives here:
    - System prompt with RBI compliance framing
    - Document categories for Phase 2 query routing
    - Hindi/Hinglish refusal message
    - Citation format

Zero changes to axonri_core needed to adapt to a new domain.
"""

from axonri_core.config import DomainConfig

# ── System prompt ─────────────────────────────────────────────────────────────
# This is the most important configuration item.
# Changes here directly affect answer quality.
# Test against the eval set after any modification.

BANKING_SYSTEM_PROMPT = """You are Axonri, a regulatory document assistant for a cooperative bank in India.
You help branch officers and compliance staff find answers in RBI regulations, Master Directions, and banking guidelines.

STRICT RULES — follow these exactly, without exception:
1. Answer ONLY using the numbered passages provided below. Never use your general knowledge or training data.
2. If the answer is not clearly stated in the provided passages, respond with EXACTLY:
   "Yeh information mere paas available documents mein nahi hai. Kripya apne compliance officer se poochein."
3. Always end your answer with the source citation in this exact format:
   [Source: {document_name}, Page {page_number}]
   Use the document name and page number from the passage header.
4. Answer in the same language the question was asked:
   - Hindi question → Hindi answer
   - English question → English answer
   - Hinglish (mixed) question → Hinglish answer
5. Be concise — 2 to 4 sentences for most answers. For regulatory limits and percentages, quote the exact value.
6. Never speculate, interpolate, or reason beyond what is explicitly written in the passages.
7. If multiple passages are relevant, synthesise them but cite ALL relevant sources.

Remember: a bank officer will act on your answer. Accuracy is more important than completeness."""


# ── Document categories for Phase 2 query routing ────────────────────────────
# Phase 1: leave this configured but unused (searches all documents)
# Phase 2: classify query into a category, filter Qdrant to that category's doc_ids
#
# doc_ids must match IngestPipeline._make_doc_id() output:
#   filename stem, lowercased, spaces/hyphens → underscores
# e.g. "UCB Credit Facilities 2025.pdf" → "ucb_credit_facilities_2025"

BANKING_DOCUMENT_CATEGORIES = {
    "credit": [
        "ucb_credit_facilities_directions_2025",
        "ucb_credit_risk_management_directions_2025",
        "ucb_concentration_risk_management_directions_2025",
        "irac_master_circular",
    ],
    "kyc": [
        "master_direction_kyc_2016",
        "pmla_guidelines",
    ],
    "governance": [
        "ucb_governance_directions_2025",
        "ucb_prudential_norms_on_capital_adequacy_2025",
        "ucb_cash_reserve_ratio_slr_directions_2025",
    ],
    "operations": [
        "ucb_branch_authorisation_directions_2025",
        "ucb_digital_banking_channels_authorisation_2025",
        "ucb_frauds_classification_reporting_directions_2025",
        "ucb_interest_rate_on_deposits_directions_2025",
    ],
    "loans": [
        "ucb_credit_facilities_directions_2025",
        "irac_master_circular",
        "master_direction_priority_sector_lending",
    ],
    "general": [],   # empty = search all documents
}


# ── Build and export the config instance ──────────────────────────────────────

banking_config = DomainConfig(
    # Identity
    domain_id="banking",
    domain_name="UCB Banking Compliance",

    # Storage — versioned so migration is safe
    collection_name="axonri_banking_v1",

    # Prompts
    system_prompt=BANKING_SYSTEM_PROMPT,
    refusal_message=(
        "Yeh information mere paas available documents mein nahi hai. "
        "Kripya apne compliance officer ya RBI guidelines check karein."
    ),
    citation_format="[Source: {doc_name}, Page {page}]",

    # Language
    primary_language="hi-en",
    stt_language_code="hi-IN",

    # Retrieval
    top_k_retrieve=20,
    top_k_rerank=5,
    chunk_size=512,
    chunk_overlap=50,
    similarity_threshold=0.0,   # no minimum threshold in Phase 1

    # Query routing (Phase 2)
    document_categories=BANKING_DOCUMENT_CATEGORIES,

    # LLM
    max_tokens=512,
    temperature=0.1,
    stop_sequences=["</answer>"],

    # UI
    ui_placeholder="RBI ke baare mein kuch poochein... (Hindi, English, ya Hinglish mein)",
    ui_app_name="Axonri — Banking Compliance",
)

# ── RBI document corpus definition ───────────────────────────────────────────
# Source of truth for which documents to download and ingest.
# Used by scripts/download_corpus.py and scripts/ingest.py

RBI_DOCUMENT_CORPUS = [
    # ── UCB-specific Master Directions (Nov 28, 2025) ──────────────────────
    {
        "doc_name": "UCB Credit Facilities Directions 2025",
        "filename":  "ucb_credit_facilities_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/277MDFF00147367D64F02899A3A756CDA9093.PDF",
        "corpus_type": "regulatory",
        "category": "credit",
        "priority": "critical",
    },
    {
        "doc_name": "UCB Credit Risk Management Directions 2025",
        "filename":  "ucb_credit_risk_management_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/280MD71ABEC5E655C4CE7816646F849E5CB29.PDF",
        "corpus_type": "regulatory",
        "category": "credit",
        "priority": "critical",
    },
    {
        "doc_name": "UCB Prudential Norms on Capital Adequacy 2025",
        "filename":  "ucb_prudential_norms_on_capital_adequacy_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/275MD3D20366A706C4C13B4FA21A3DC0451A1.PDF",
        "corpus_type": "regulatory",
        "category": "governance",
        "priority": "critical",
    },
    {
        "doc_name": "UCB Governance Directions 2025",
        "filename":  "ucb_governance_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/273MD1E2C8ADF7F3D4881933547E0AAABCFA4.PDF",
        "corpus_type": "regulatory",
        "category": "governance",
        "priority": "high",
    },
    {
        "doc_name": "UCB Cash Reserve Ratio and SLR Directions 2025",
        "filename":  "ucb_cash_reserve_ratio_slr_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/274MD3A0AEE03DF1B4F39BB0F0B91BFC73A05.PDF",
        "corpus_type": "regulatory",
        "category": "governance",
        "priority": "high",
    },
    {
        "doc_name": "UCB Interest Rate on Deposits Directions 2025",
        "filename":  "ucb_interest_rate_on_deposits_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/276MD926CB0F1D85C4C7981A81F01AAEE0D13.PDF",
        "corpus_type": "regulatory",
        "category": "operations",
        "priority": "high",
    },
    {
        "doc_name": "UCB Credit Information Reporting Directions 2025",
        "filename":  "ucb_credit_information_reporting_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/279MD3334DC0D4F8F43068FA37F74DED62382.PDF",
        "corpus_type": "regulatory",
        "category": "credit",
        "priority": "high",
    },
    {
        "doc_name": "UCB Frauds Classification and Reporting Directions 2025",
        "filename":  "ucb_frauds_classification_reporting_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/278MD2C704B1C34BF4E1BB8F6B710190D4E6C.PDF",
        "corpus_type": "regulatory",
        "category": "operations",
        "priority": "high",
    },
    {
        "doc_name": "UCB Branch Authorisation Directions 2025",
        "filename":  "ucb_branch_authorisation_directions_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/271MD5F6E28F2C5AF4B92AE44048FD3C21405.PDF",
        "corpus_type": "regulatory",
        "category": "operations",
        "priority": "medium",
    },
    {
        "doc_name": "UCB Digital Banking Channels Authorisation 2025",
        "filename":  "ucb_digital_banking_channels_authorisation_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/385MDE9EEBCE5D5EA40C5AD9FD122507E94F8.PDF",
        "corpus_type": "regulatory",
        "category": "operations",
        "priority": "medium",
    },
    {
        "doc_name": "UCB Licensing Scheduling and Regulatory Classification 2025",
        "filename":  "ucb_licensing_scheduling_regulatory_classification_2025.pdf",
        "url": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/269MDB68791ED3DA4407596FC88446FC24DF3.PDF",
        "corpus_type": "regulatory",
        "category": "governance",
        "priority": "medium",
    },
    # ── Cross-cutting Master Directions ─────────────────────────────────────
    {
        "doc_name": "Master Direction KYC 2016 (Updated 2025)",
        "filename":  "master_direction_kyc_2016.pdf",
        "url": "https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
        "corpus_type": "regulatory",
        "category": "kyc",
        "priority": "critical",
        "note": "Download PDF from the page — direct PDF link varies",
    },
    {
        "doc_name": "Master Direction Priority Sector Lending",
        "filename":  "master_direction_priority_sector_lending.pdf",
        "url": "https://www.rbi.org.in/scripts/BS_ViewMasterDirections.aspx?did=343",
        "corpus_type": "regulatory",
        "category": "loans",
        "priority": "critical",
        "note": "Download PDF from the page",
    },
    {
        "doc_name": "Master Direction Frauds Classification Reporting UCBs",
        "filename":  "master_direction_frauds_ucbs.pdf",
        "url": "https://www.rbi.org.in/scripts/BS_ViewMasterDirections.aspx?did=414",
        "corpus_type": "regulatory",
        "category": "operations",
        "priority": "high",
        "note": "Download PDF from the page",
    },
    {
        "doc_name": "IRAC Master Circular NPA Classification",
        "filename":  "irac_master_circular.pdf",
        "url": "https://www.rbi.org.in",
        "corpus_type": "regulatory",
        "category": "credit",
        "priority": "critical",
        "note": "Search rbi.org.in for 'Master Circular IRAC UCB 2025' — URL changes annually",
    },
]

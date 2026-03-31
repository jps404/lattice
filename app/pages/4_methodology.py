"""Methodology page — academic research documentation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from components.sidebar import render_sidebar
from components.theme import page_header

st.set_page_config(page_title="Methodology — LATTICE", layout="wide")
render_sidebar()

st.markdown(page_header("Methodology", "Research design, data sources, and analytical procedures"), unsafe_allow_html=True)

st.markdown("""
<div style="max-width:720px;">

<p style="font-size:0.65rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:1.5rem;">
    Tulane University · Department of Political Science · Working Paper · 2026</p>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">1. Introduction</h2>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:1.5rem;">
LATTICE (Legislative Analysis Through Transparency, Intelligence, and Civic Engagement) is a
computational platform designed to lower informational barriers in state legislative politics.
State legislatures process thousands of bills per session, most of which receive no media coverage
and minimal public scrutiny. Simultaneously, campaign finance disclosure data — while legally
mandated — is difficult for citizens to connect to specific legislative actions. LATTICE addresses
this gap by combining large language model analysis, campaign contribution records, and predictive
modeling into a unified transparency instrument.
</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:1.5rem;">
The platform currently covers the Louisiana state legislature as a proof-of-concept. Louisiana
was selected because of its unique political culture, the availability of electronic campaign
finance filings, and the practical relevance of transparency tools in a state with historically
low legislative accountability rankings (Center for Public Integrity, 2015).
</p>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">2. Data Collection</h2>

<p style="font-weight:500;font-size:0.9rem;color:#1c1917;margin:1rem 0 0.3rem 0;">2.1 Legislative data</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
Bill data is sourced from the LegiScan API, which provides structured access to state legislative
records including bill text, sponsorship information, committee assignments, vote records, and
status tracking. For each bill, we retrieve the full document text via LegiScan's base64-encoded
text endpoint. Louisiana bills are primarily filed as PDF documents; we extract plain text using
PyMuPDF (fitz). The current dataset covers the 2025 Regular Session, 2025 Special Sessions,
and the 2026 Regular Session.
</p>

<p style="font-weight:500;font-size:0.9rem;color:#1c1917;margin:1rem 0 0.3rem 0;">2.2 Campaign finance data</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
Campaign contributions are sourced from the Louisiana Board of Ethics electronic filing system.
We use the complete contribution records for the 2024–2027 filing period. Individual contributions
are linked to legislators via name matching between Ethics Administration filer records and
LegiScan legislator records. Matching achieves coverage of approximately 90% of active legislators.
Contributions are classified by type (individual, business, PAC, candidate self-funding) as
reported in the original filings. We aggregate at the donor and donor-type level for visualization.
</p>
<p style="font-size:0.82rem;color:#78716c;line-height:1.7;margin-bottom:1.5rem;">
<em>Note on data currency:</em> Campaign finance filings reflect legally mandated disclosure and may
lag actual fundraising activity. Some contributions may be reported in aggregate for small-dollar
donors. The data reflects reported contributions only and does not capture independent expenditures,
dark money, or other forms of political spending not subject to state disclosure requirements.
</p>

<p style="font-weight:500;font-size:0.9rem;color:#1c1917;margin:1rem 0 0.3rem 0;">2.3 Statute references</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:1.5rem;">
When bills reference existing Louisiana law (e.g., "R.S. 30:4(A)(1)"), we extract these citations
using regular expressions calibrated to Louisiana statutory citation formats, then fetch the
referenced statute text from the Louisiana Legislature website (legis.la.gov). This context is
provided to the language model during bill analysis to enable accurate assessment of what
the proposed legislation would change in existing law.
</p>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">3. Bill Analysis Pipeline</h2>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
Each bill undergoes a three-pass analysis pipeline using Anthropic's Claude language model.
We use Claude Haiku for bulk processing (cost: ~$0.03 per bill) and Claude Sonnet for
bills flagged as high-controversy for deeper analysis.
</p>

<div class="lc" style="margin-bottom:0.5rem;">
    <p style="font-weight:500;font-size:0.85rem;color:#1c1917;margin:0 0 0.3rem 0;">Pass 1: Statute Reference Extraction</p>
    <p style="font-size:0.82rem;color:#57534e;line-height:1.7;margin:0;">
    Combines regex-based extraction of Louisiana Revised Statute (R.S.) and Civil Code (C.C.)
    citations with LLM validation. The model identifies citations that regex may miss (e.g.,
    indirect references, Title-level citations). Referenced statute text is fetched from
    legis.la.gov and provided as context for Pass 2.</p>
</div>

<div class="lc" style="margin-bottom:0.5rem;">
    <p style="font-weight:500;font-size:0.85rem;color:#1c1917;margin:0 0 0.3rem 0;">Pass 2: Plain-Language Analysis</p>
    <p style="font-size:0.82rem;color:#57534e;line-height:1.7;margin:0;">
    The model receives the complete bill text and referenced statute context with instructions to:
    (a) summarize what the bill substantively does in 2–4 sentences, avoiding official title language;
    (b) enumerate specific changes to existing law;
    (c) identify beneficiaries and parties adversely affected;
    (d) flag hidden provisions, exemptions, or loopholes.
    The model also classifies the bill by policy area and generates a controversy score.</p>
</div>

<div class="lc" style="margin-bottom:0.5rem;">
    <p style="font-weight:500;font-size:0.85rem;color:#1c1917;margin:0 0 0.3rem 0;">Pass 3: Money Trail Analysis</p>
    <p style="font-size:0.82rem;color:#57534e;line-height:1.7;margin:0;">
    After campaign finance data is loaded, the model receives the bill summary, sponsor's
    top donors by industry, and identified beneficiaries. It assesses alignment between
    donor interests and bill provisions, generating a donor alignment score (0–1) and
    specific conflict flags. The model is prompted to identify patterns, not make accusations.</p>
</div>

<p style="font-weight:500;font-size:0.9rem;color:#1c1917;margin:1.5rem 0 0.3rem 0;">3.1 Controversy score</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
The controversy score (0–1) is a composite heuristic generated by the language model
during Pass 2. The model is instructed to evaluate along these dimensions:
</p>
<ul style="font-size:0.82rem;color:#57534e;line-height:1.8;margin-bottom:1.5rem;">
    <li><span style="font-weight:500;color:#44403c;">Distributional impact</span> — Does the bill create asymmetric winners and losers?</li>
    <li><span style="font-weight:500;color:#44403c;">Rights modification</span> — Does it remove existing protections or create new governmental powers?</li>
    <li><span style="font-weight:500;color:#44403c;">Vulnerable populations</span> — Are impacts concentrated on groups with limited political voice?</li>
    <li><span style="font-weight:500;color:#44403c;">Public salience</span> — Does the bill touch on culturally or politically divisive topics?</li>
    <li><span style="font-weight:500;color:#44403c;">Opacity</span> — Does the bill contain provisions that may not be apparent from its title?</li>
</ul>
<p style="font-size:0.82rem;color:#78716c;line-height:1.7;margin-bottom:1.5rem;">
<em>Validity note:</em> The controversy score is a heuristic generated by an AI model, not
a validated political science measure. It should be interpreted as a rough salience
indicator, not a normative judgment. Scores are not comparable across policy areas
(e.g., a 0.7 in criminal justice reflects different dynamics than a 0.7 in taxation).
We present it as a sorting mechanism, not an analytical finding.
</p>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">4. Passage Prediction</h2>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
We model bill passage probability using logistic regression, selected for interpretability
over predictive performance. The dependent variable is binary (1 = Passed or Enrolled,
0 = Failed or Vetoed).
</p>
<p style="font-weight:500;font-size:0.85rem;color:#1c1917;margin:0.75rem 0 0.3rem 0;">Feature set:</p>
<ul style="font-size:0.82rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
    <li><span style="font-weight:500;color:#44403c;">Majority party alignment</span> — Binary indicator: sponsor belongs to chamber majority party (Republican)</li>
    <li><span style="font-weight:500;color:#44403c;">Co-sponsor count</span> — Number of co-sponsors (continuous)</li>
    <li><span style="font-weight:500;color:#44403c;">Chamber</span> — Binary indicator for House vs. Senate origin</li>
    <li><span style="font-weight:500;color:#44403c;">Bipartisan support</span> — Binary: sponsors include members of more than one party</li>
    <li><span style="font-weight:500;color:#44403c;">Controversy score</span> — AI-generated score from Pass 2 (continuous, 0–1)</li>
    <li><span style="font-weight:500;color:#44403c;">Policy area</span> — One-hot encoded categorical variable (12 categories)</li>
    <li><span style="font-weight:500;color:#44403c;">Sponsor donations</span> — Total campaign contributions to primary sponsor (continuous)</li>
</ul>

<p style="font-weight:500;font-size:0.85rem;color:#1c1917;margin:0.75rem 0 0.3rem 0;">Evaluation:</p>
<p style="font-size:0.82rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
Model is trained on resolved bills from the 2025 Regular Session and evaluated via 5-fold
cross-validation. We report the Brier score as our primary evaluation metric — the mean
squared error between predicted probabilities and actual binary outcomes. The Brier score
is a proper scoring rule that rewards calibrated probabilistic predictions (Brier, 1950):
lower is better, with 0 representing perfect prediction and 0.25 representing a coin flip.
</p>
<p style="font-size:0.82rem;color:#78716c;line-height:1.7;margin-bottom:1.5rem;">
<em>Limitations:</em> The training set is heavily imbalanced toward passage (most introduced bills
in Louisiana do pass committee). The model captures correlational patterns in legislative
structure, not causal mechanisms. Features like co-sponsor count may proxy for legislative
negotiation that is unobservable in our data. Predictions should be treated as baseline
rates conditional on observable characteristics, not as causal forecasts.
</p>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">5. Pattern Detection</h2>

<p style="font-weight:500;font-size:0.9rem;color:#1c1917;margin:1rem 0 0.3rem 0;">5.1 Model legislation</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
We screen bills for language associated with known model legislation sources, particularly
the American Legislative Exchange Council (ALEC) and the State Policy Network (SPN).
Detection uses keyword matching against a curated dictionary of phrases characteristic of
widely documented model bills (e.g., "right to work," "stand your ground," "certificate of need,"
"regulatory sandbox"). A match indicates textual similarity to known templates; it does not
establish provenance or intent.
</p>
<p style="font-size:0.82rem;color:#78716c;line-height:1.7;margin-bottom:1.5rem;">
<em>Future work:</em> We plan to implement embedding-based similarity detection using
text-embedding-3-small (OpenAI) and pgvector cosine similarity search, which would enable
detection of semantically similar legislation even when language has been substantially modified.
</p>

<p style="font-weight:500;font-size:0.9rem;color:#1c1917;margin:1rem 0 0.3rem 0;">5.2 Conflict-of-interest flags</p>
<p style="font-size:0.85rem;color:#57534e;line-height:1.8;margin-bottom:0.75rem;">
The platform generates automated flags when patterns emerge between a legislator's campaign
donors and their sponsored legislation. Two detection methods are currently implemented:
</p>
<p style="font-size:0.82rem;color:#57534e;line-height:1.8;margin-bottom:0.5rem;">
<span style="font-weight:500;color:#44403c;">Donor–beneficiary alignment.</span>
Pass 3 of the bill analysis pipeline compares the industries of a sponsor's top donors
against the industries identified as beneficiaries of the bill. An alignment score (0–1)
is computed by the language model. Scores above 0.5 generate a flag.
</p>
<p style="font-size:0.82rem;color:#57534e;line-height:1.8;margin-bottom:0.5rem;">
<span style="font-weight:500;color:#44403c;">Contribution timing.</span>
Flags cases where the primary sponsor received aggregate contributions exceeding $2,000 from
a single donor within 180 days preceding the bill's introduction date. The window is calibrated
to Louisiana's legislative calendar.
</p>
<p style="font-size:0.82rem;color:#78716c;line-height:1.8;margin-bottom:1.5rem;">
<em>Important caveat:</em> Campaign contributions are legal, constitutionally protected activity.
A statistical correlation between donations and legislative action does not establish a
causal link, quid pro quo arrangement, or any form of corruption. These flags are designed
to facilitate public scrutiny, not to level accusations. The literature on campaign finance
influence finds mixed evidence on whether contributions "buy" votes versus "buy" access
(Ansolabehere et al., 2003; Stratmann, 2005). Users should interpret these flags as
starting points for inquiry, not conclusions.
</p>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">6. Data Sources &amp; Infrastructure</h2>
<div class="lc" style="margin-bottom:1.5rem;">
    <p style="font-size:0.82rem;color:#57534e;line-height:1.9;margin:0;">
    <span style="font-weight:500;color:#1c1917;">Legislative data:</span> LegiScan API (legiscan.com) — bill text, sponsors, status, vote history, amendments<br>
    <span style="font-weight:500;color:#1c1917;">Campaign finance:</span> Louisiana Board of Ethics electronic filings (ethics.la.gov) — 2024–2027<br>
    <span style="font-weight:500;color:#1c1917;">Statute text:</span> Louisiana Legislature (legis.la.gov) — Revised Statutes, Civil Code<br>
    <span style="font-weight:500;color:#1c1917;">NLP:</span> Anthropic Claude Haiku 4.5 (bulk analysis), Claude Sonnet 4.5 (deep analysis)<br>
    <span style="font-weight:500;color:#1c1917;">Database:</span> PostgreSQL on Supabase with pgvector extension<br>
    <span style="font-weight:500;color:#1c1917;">ML:</span> scikit-learn (logistic regression, cross-validation)<br>
    <span style="font-weight:500;color:#1c1917;">Frontend:</span> Streamlit
    </p>
</div>

<h2 style="font-size:1.4rem;margin-bottom:0.4rem;">References</h2>
<p style="font-size:0.8rem;color:#57534e;line-height:1.8;margin-bottom:0.3rem;">
Ansolabehere, S., de Figueiredo, J. M., &amp; Snyder, J. M. (2003). Why is there so little
money in U.S. politics? <em>Journal of Economic Perspectives</em>, 17(1), 105–130.
</p>
<p style="font-size:0.8rem;color:#57534e;line-height:1.8;margin-bottom:0.3rem;">
Brier, G. W. (1950). Verification of forecasts expressed in terms of probability.
<em>Monthly Weather Review</em>, 78(1), 1–3.
</p>
<p style="font-size:0.8rem;color:#57534e;line-height:1.8;margin-bottom:0.3rem;">
Stratmann, T. (2005). Some talk: Money in politics. A (partial) review of the literature.
<em>Public Choice</em>, 124(1), 135–156.
</p>
<p style="font-size:0.8rem;color:#57534e;line-height:1.8;margin-bottom:0.3rem;">
Center for Public Integrity. (2015). State Integrity Investigation. Washington, DC.
</p>

<p style="font-size:0.68rem;color:#a8a29e;margin-top:2rem;line-height:1.7;">
    LATTICE v0.1 · Tulane University · Department of Political Science · 2026<br>
    All analysis links to original bill text. Source code available for reproducibility.
</p>

</div>
""", unsafe_allow_html=True)

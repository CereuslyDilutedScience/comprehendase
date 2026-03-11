# CLAUDE.md

# Project Overview
Comprehendase is a web application used to aid in the comprehension of scientific terminology.
mulit-level text extraction, OLS-4-API lookup, rendered PDF output. 
https://cereuslydilutedscience.github.io/comprehendase/
This project is in the an early stage of development. 

# Key components for this phase of development
*	Only PDF files are supported
*	Positional metadata must be preserved throughout the pipeline.
*	Scientific journal articles contain diverse formatting styles and complex layouts, this must be taken into consideration. 
*	The filtering and sorting of text before ontology look-up must be comprehensive for efficiency. 
*	Read order from positonal metadata must be reconstructed before ontology lookup.
*	The backend uses google cloud build deployment.
*	OLS4-API has specific batch request limitations per request. maximum lookup is ~500 words, decreasing to ~250 for phrase lookup. 
	further information can be found here: https://www.ebi.ac.uk/ols4/
*	The output must be the original rendered PDF.
*	highlight boxes must be positioned percisely over the original PDF term of the rendered PDF.
*	Tool-tip containing the term definition must appear upon hovering over a highlighted term. 
*	Testing files must be built and updated with each appropriate codebase change. 

# ENVIRONMENT
*	Runtime: Python 3.11-slim-bookworm
*	Packages defined in requirements.txt
*	Docker file containerization
*	cloudbuild.yaml for google cloud build deployment 

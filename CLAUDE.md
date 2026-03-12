# CLAUDE.md

# Project Overview
Comprehendase is a web application used to aid in the comprehension of scientific terminology appearing within scientific journal articles.
Pipeline includes: mulit-level text extraction, OLS4-API lookup, rendered PDF output. 
https://cereuslydilutedscience.github.io/comprehendase/
This project is in a very early stage of development. 

# ENVIRONMENT
*	Runtime: Python 3.11-slim-bookworm
*	Packages defined in requirements.txt
*	Docker file containerization
*	cloudbuild.yaml for google cloud build deployment 

# Testing
*	Testing should be developed with pytest utilizing pytest plug-ins when needed.
*	mock OLS4-API testing should be implemented
*	Testing files must be updated with each appropriate codebase change.
*	Some PDF testing files are included within the /test directory. 

# Key components for this phase of development
*	Only PDF file uploads are supported
*	Positional metadata must be preserved throughout the pipeline.
*	Scientific journal articles contain diverse formatting styles and complex layouts, this must be taken into consideration. 
*	The filtering and sorting of text before ontology look-up must be comprehensive for efficiency. 
*	OLS4-API has specific batch request limitations per request. maximum lookup is ~500 words, decreasing to ~250 for phrase lookup. 
	further information can be found here: https://www.ebi.ac.uk/ols4/
*	OLS4-API has been chosen based on the allowance of batch requests.
*	The output must provide highlights positioned percisely to overlay the original rendered PDF.
*	definitions must appear within a tool-tip upon hovering over a highlighted term. 

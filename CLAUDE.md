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


# Key components for this phase of development
*	Only PDF file uploads are supported
*	Positional metadata must be preserved throughout the pipeline.
*	Scientific journal articles contain diverse formatting styles and complex layouts, this must be taken into consideration. 
*	OLS4-API has specific batch request limitations per request. maximum per request lookup is ~500 words, decreasing to ~250 for phrase lookup. 
	further information on the API can be found here: https://www.ebi.ac.uk/ols4/

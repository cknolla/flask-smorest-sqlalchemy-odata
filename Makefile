PROJECT_ROOT=$(shell git rev-parse --show-toplevel)

blackformat:
	black --check $(PROJECT_ROOT)

lintcheck:
	flake8

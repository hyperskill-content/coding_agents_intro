#!/bin/sh
# Check that the environment is ready for running the tests.
python3 --version
python3 -c "import unittest" && echo "unittest: ok"
env | grep -E '^OPENAI_(API_KEY|BASE_URL)=' | sed -E 's/^(OPENAI_API_KEY=.{4}).*/\1****/' > env_check.txt
echo "Environment OK"

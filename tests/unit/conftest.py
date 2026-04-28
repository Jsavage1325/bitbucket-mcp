import os

# Ensure the server module can be imported without real credentials.
os.environ.setdefault("BITBUCKET_ACCESS_TOKEN", "test-token")

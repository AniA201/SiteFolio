import os

# Tests run against the bundled sample data, never the local real-data build, and never call a live model.
os.environ["PLUMBLINE_DATA"] = "sample"
os.environ["PLUMBLINE_AGENT"] = "replay"
os.environ["LANGSMITH_TRACING"] = "false"  # tests never send traces
os.environ["PLUMBLINE_SOLANA"] = "off"  # tests never send devnet transactions
os.environ["TIGER_DATABASE_URL"] = ""  # tests never write to Tiger Cloud (test_tiger.py uses TIGER_TEST_URL)
os.environ["PLUMBLINE_BEDROCK"] = "off"  # tests never call AWS Bedrock

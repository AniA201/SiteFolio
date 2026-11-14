import os

# Tests run against the bundled sample data, never the local real-data build, and never call a live model.
os.environ["PLUMBLINE_DATA"] = "sample"
os.environ["PLUMBLINE_AGENT"] = "replay"
os.environ["LANGSMITH_TRACING"] = "false"  # tests never send traces
os.environ["PLUMBLINE_SOLANA"] = "off"  # tests never send devnet transactions

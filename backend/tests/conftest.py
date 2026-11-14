import os

# Tests run against the bundled sample data, never the local real-data build.
os.environ["PLUMBLINE_DATA"] = "sample"

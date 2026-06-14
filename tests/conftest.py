import os
import sys

# Dynamically add the src/ directory to python path for all tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

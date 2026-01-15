"""
Purple Computer - The Calm Computer for Kids

A Textual TUI application providing:
- Ask Mode: Math and emoji REPL
- Play Mode: Music and art grid
- Write Mode: Simple text editor

Designed for ages 3-8. Safe, calm, distraction-free.
"""

# Suppress ONNX runtime warnings BEFORE any imports that might load it
# This must happen at package init, before piper or any ML libs are imported
import os as _os
_os.environ.setdefault('ORT_LOGGING_LEVEL', '3')  # ERROR level only
_os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')  # Suppress TensorFlow too

__version__ = "2.0.0"

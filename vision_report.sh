#!/bin/bash
# Generate Vision Audit Report
cd /opt/jayce
./venv/bin/python3 -c "from vision_audit import generate_summary; print(generate_summary())"

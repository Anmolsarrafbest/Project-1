"""Quick test script for validation service."""
import logging
from services.validator import ValidationService

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test files
test_files = {
    "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test Calculator</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container">
        <h1>Calculator</h1>
        <div id="result">0</div>
        <button onclick="calculate()">Calculate</button>
    </div>
    <script>
        function calculate() {
            const sum = 2 + 2;
            document.getElementById('result').textContent = sum;
        }
    </script>
</body>
</html>""",
    
    "LICENSE": """MIT License

Copyright (c) 2025 Test Project

Permission is hereby granted, free of charge...""",
    
    "README.md": """# Test Calculator

## Overview

This is a professional calculator application.

## Features

- Addition
- Subtraction

## Setup

Open index.html in browser.
"""
}

test_checks = [
    "Repo has MIT license",
    "README.md is professional and complete",
    "Page has element with id='result'",
    "Page loads Bootstrap 5 from CDN",
    "Calculator performs basic arithmetic operations"
]

# Run tests
validator = ValidationService()

print("\n" + "=" * 70)
print("TESTING STATIC FILE VALIDATION")
print("=" * 70)

static_result = validator.validate_static_files(test_files, test_checks)
print(f"\nPassed: {static_result['passed']}")
print(f"Errors: {len(static_result['errors'])}")
print(f"Warnings: {len(static_result['warnings'])}")

if static_result['errors']:
    print("\nErrors:")
    for error in static_result['errors']:
        print(f"  ❌ {error}")

if static_result['warnings']:
    print("\nWarnings:")
    for warning in static_result['warnings']:
        print(f"  ⚠️  {warning}")

print("\n" + "=" * 70)
print("TESTING CHECKS VALIDATION")
print("=" * 70)

checks_result = validator.validate_against_checks(test_files, test_checks)
print(f"\nPassed: {checks_result['passed_count']}/{checks_result['total_checks']}")
print(f"Failed: {checks_result['failed_count']}")
print(f"Unknown: {checks_result['unknown_count']}")
print(f"All passed: {checks_result['all_passed']}")

print("\nDetailed results:")
for result in checks_result['results']:
    status = "✓" if result['passed'] == True else "✗" if result['passed'] == False else "⚠"
    print(f"  {status} {result['check']}")
    print(f"    → {result['message']}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)

"""Test targeted fix functionality."""
import logging
from services.llm_generator import LLMGenerator
from services.validator import ValidationService
from config import get_settings

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

settings = get_settings()

# Test files with a bad README (too short)
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

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...""",
    
    # SHORT README - will fail validation
    "README.md": """# Calculator

Simple calculator app."""
}

test_checks = [
    "Repo has MIT license",
    "README.md is professional and complete",  # This will FAIL
    "Page has element with id='result'",
    "Page loads Bootstrap 5 from CDN",
]

print("\n" + "=" * 70)
print("INITIAL VALIDATION")
print("=" * 70)

validator = ValidationService()
initial_validation = validator.validate_against_checks(test_files, test_checks)

print(f"\nInitial score: {initial_validation['passed_count']}/{initial_validation['total_checks']}")

failed_checks = [r for r in initial_validation["results"] if r["passed"] == False]

if failed_checks:
    print(f"\nFailed checks: {len(failed_checks)}")
    for check in failed_checks:
        print(f"  ✗ {check['check']}: {check['message']}")
    
    print("\n" + "=" * 70)
    print("ATTEMPTING TARGETED FIX")
    print("=" * 70)
    
    # Initialize LLM generator
    generator = LLMGenerator(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url
    )
    
    # Try to fix
    fixed_files = generator.fix_validation_failures(
        test_files,
        failed_checks,
        "test-calculator"
    )
    
    print("\n" + "=" * 70)
    print("RE-VALIDATION AFTER FIX")
    print("=" * 70)
    
    final_validation = validator.validate_against_checks(fixed_files, test_checks)
    
    print(f"\nFinal score: {final_validation['passed_count']}/{final_validation['total_checks']}")
    print(f"Improvement: +{final_validation['passed_count'] - initial_validation['passed_count']} checks")
    
    print("\nFixed README.md:")
    print("-" * 70)
    print(fixed_files.get("README.md", "NOT FOUND")[:500])
    print("-" * 70)
    
    print("\nComparison:")
    print(f"  Original README length: {len(test_files['README.md'])} chars")
    print(f"  Fixed README length: {len(fixed_files.get('README.md', ''))} chars")
else:
    print("\n✓ All checks passed initially, no fix needed!")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)

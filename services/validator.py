"""Validation service to verify generated code meets requirements."""
import logging
import re
from typing import Dict, List, Any
import httpx

logger = logging.getLogger(__name__)


class ValidationService:
    """Validate generated code against checks and requirements."""
    
    def __init__(self):
        """Initialize validator."""
        pass
    
    def validate_static_files(
        self,
        files: Dict[str, str],
        checks: List[str]
    ) -> Dict[str, Any]:
        """
        Validate generated files before deployment.
        
        Args:
            files: Dictionary of {filename: content}
            checks: List of validation checks
        
        Returns:
            Dict with validation results
        """
        logger.info("Starting static file validation...")
        
        errors = []
        warnings = []
        
        # Basic file existence checks
        if "index.html" not in files:
            errors.append("Missing required file: index.html")
        
        if "LICENSE" not in files:
            errors.append("Missing required file: LICENSE")
        
        if "README.md" not in files:
            errors.append("Missing required file: README.md")
        
        # Check files are not empty
        for filename in ["index.html", "LICENSE", "README.md"]:
            if filename in files:
                content = files[filename]
                if isinstance(content, bytes):
                    if len(content) == 0:
                        errors.append(f"{filename} is empty (0 bytes)")
                elif not content.strip():
                    errors.append(f"{filename} is empty or whitespace only")
        
        # Validate LICENSE is MIT
        if "LICENSE" in files:
            license_content = files["LICENSE"]
            if isinstance(license_content, bytes):
                license_content = license_content.decode('utf-8', errors='ignore')
            
            license_lower = license_content.lower()
            if "mit license" not in license_lower and "mit" not in license_lower[:200]:
                errors.append("LICENSE file does not appear to be MIT license")
        
        # Validate README.md quality
        if "README.md" in files:
            readme = files["README.md"]
            if isinstance(readme, bytes):
                readme = readme.decode('utf-8', errors='ignore')
            
            # Check minimum length
            if len(readme) < 150:
                warnings.append(f"README.md is very short ({len(readme)} chars)")
            
            # Check for headings
            if not re.search(r'^#+\s', readme, re.MULTILINE):
                warnings.append("README.md lacks markdown headings")
            
            # Check for basic structure
            if "##" not in readme:
                warnings.append("README.md lacks section headings (##)")
        
        # Validate HTML structure
        if "index.html" in files:
            html = files["index.html"]
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='ignore')
            
            html_lower = html.lower()
            
            # Check for escaped characters (critical quality issue)
            escaped_char_issues = self._check_for_escaped_characters(html, "index.html")
            if escaped_char_issues:
                errors.extend(escaped_char_issues)
            
            # Check DOCTYPE
            if "<!doctype" not in html_lower:
                warnings.append("index.html missing DOCTYPE declaration")
            
            # Check basic HTML structure
            if "<html" not in html_lower:
                errors.append("index.html missing <html> tag")
            
            if "<body" not in html_lower:
                errors.append("index.html missing <body> tag")
            
            if "<head" not in html_lower:
                warnings.append("index.html missing <head> tag")
            
            # Check for title
            if "<title" not in html_lower:
                warnings.append("index.html missing <title> tag")
        
        # Validate JavaScript files for functionality
        js_files = [f for f in files.keys() if f.endswith('.js')]
        if js_files:
            for js_file in js_files:
                js_content = files[js_file]
                if isinstance(js_content, bytes):
                    js_content = js_content.decode('utf-8', errors='ignore')
                
                js_issues = self._check_javascript_functionality(js_content, js_file)
                warnings.extend(js_issues)
        
        # Also check embedded JavaScript in HTML
        if "index.html" in files:
            html = files["index.html"]
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='ignore')
            
            # Extract script tags
            script_match = re.search(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
            if script_match:
                embedded_js = script_match.group(1)
                js_issues = self._check_javascript_functionality(embedded_js, "index.html (embedded)")
                warnings.extend(js_issues)
        
        result = {
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "total_files": len(files),
            "files_validated": ["index.html", "LICENSE", "README.md"]
        }
        
        logger.info(f"Static validation: {len(errors)} errors, {len(warnings)} warnings")
        return result
    
    def _check_for_escaped_characters(self, content: str, filename: str) -> List[str]:
        """
        Check if content contains literal escaped characters like \\n or \\" 
        which indicate the LLM returned improperly formatted code.
        
        Args:
            content: File content to check
            filename: Name of file being checked
        
        Returns:
            List of error messages
        """
        errors = []
        
        # Check first 1000 characters for escaped sequences
        # (if they're at the start, the whole file is likely broken)
        sample = content[:1000]
        
        # Pattern 1: Literal \n sequences (not actual newlines)
        # In properly formatted HTML, we should have actual newlines, not the two-character sequence \n
        if '\\n' in sample:
            # Count occurrences
            count = sample.count('\\n')
            errors.append(
                f"{filename}: Contains {count}+ literal '\\n' sequences - "
                "LLM returned escaped text instead of actual newlines"
            )
        
        # Pattern 2: Literal \" sequences  
        if '\\"' in sample:
            count = sample.count('\\"')
            errors.append(
                f"{filename}: Contains {count}+ literal '\\\"' sequences - "
                "LLM returned escaped quotes instead of actual quotes"
            )
        
        # Pattern 3: Literal \t sequences
        if '\\t' in sample:
            count = sample.count('\\t')
            errors.append(
                f"{filename}: Contains {count}+ literal '\\t' sequences - "
                "LLM returned escaped tabs"
            )
        
        # Pattern 4: Check if HTML tags are malformed
        if filename.endswith('.html'):
            # If we see patterns like <html\\n or lang=\\"en\\", it's broken
            if re.search(r'<\w+\\n', sample) or re.search(r'=\\"[^"]*\\"', sample):
                errors.append(
                    f"{filename}: HTML tags contain escaped characters - "
                    "file is malformed"
                )
        
        return errors
    
    def _check_javascript_functionality(self, js_code: str, source: str) -> List[str]:
        """
        Check if JavaScript code has common issues that prevent functionality.
        
        Args:
            js_code: JavaScript code to analyze
            source: Source file name for error messages
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Skip check if code is too short (likely just comments or minimal)
        lines = [l.strip() for l in js_code.split('\n') if l.strip() and not l.strip().startswith('//')]
        if len(lines) < 3:
            return warnings
        
        js_lower = js_code.lower()
        
        # Check 1: Interactive elements without event handlers
        has_button_refs = any(word in js_lower for word in ['button', 'btn', 'click'])
        has_event_handlers = any(pattern in js_code for pattern in [
            'addEventListener',
            '.click(',
            '.on(',
            'onclick',
            '@click'
        ])
        
        if has_button_refs and not has_event_handlers:
            warnings.append(
                f"{source}: References buttons but no event handlers found - "
                "interactive elements may not work"
            )
        
        # Check 2: Form handling without submit handler
        has_form_refs = any(word in js_lower for word in ['form', 'submit', 'input'])
        has_form_handlers = any(pattern in js_code for pattern in [
            '.submit(',
            'onsubmit',
            'addEventListener("submit"',
            "addEventListener('submit'"
        ])
        
        if has_form_refs and 'form' in js_lower and not has_form_handlers:
            warnings.append(
                f"{source}: References forms but no submit handler found - "
                "form submission may not be handled"
            )
        
        # Check 3: TODO or placeholder comments
        if 'TODO' in js_code or 'todo' in js_code:
            warnings.append(
                f"{source}: Contains TODO comments - "
                "code may have incomplete implementations"
            )
        
        if 'placeholder' in js_lower or 'fixme' in js_lower:
            warnings.append(
                f"{source}: Contains placeholder/FIXME comments - "
                "code may be incomplete"
            )
        
        # Check 4: Event handlers but no actual logic
        # If we have addEventListener but very little code, it might be incomplete
        if 'addEventListener' in js_code or '.click(' in js_code:
            # Count actual logic lines (not comments, not just brackets)
            logic_lines = [
                l for l in lines 
                if l and l not in ['{', '}', '});', '};'] 
                and not l.startswith('//') 
                and not l.startswith('/*')
            ]
            
            if len(logic_lines) < 5:
                warnings.append(
                    f"{source}: Has event handlers but very little logic ({len(logic_lines)} lines) - "
                    "functionality may be incomplete"
                )
        
        # Check 5: Console.log but no actual DOM manipulation
        has_console_log = 'console.log' in js_code
        has_dom_manipulation = any(pattern in js_code for pattern in [
            '.appendChild',
            '.innerHTML',
            '.innerText',
            '.textContent',
            '.createElement',
            '.remove',
            '.classList',
            '.style',
            '.setAttribute',
            '$(',  # jQuery
            'document.querySelector',
            'document.getElementById'
        ])
        
        if has_console_log and not has_dom_manipulation and len(lines) > 5:
            warnings.append(
                f"{source}: Has console.log but no DOM manipulation - "
                "may be logging without actual UI updates"
            )
        
        return warnings
    
    def validate_against_checks(
        self,
        files: Dict[str, str],
        checks: List[str]
    ) -> Dict[str, Any]:
        """
        Validate generated code against specific checks.
        
        Args:
            files: Dictionary of {filename: content}
            checks: List of check strings from IITM
        
        Returns:
            Dict with per-check validation results
        """
        logger.info(f"Validating against {len(checks)} checks...")
        
        results = []
        
        for check in checks:
            check_result = self._validate_single_check(files, check)
            results.append(check_result)
            
            status_icon = "✓" if check_result["passed"] else "✗" if check_result["passed"] == False else "⚠"
            logger.info(f"  {status_icon} {check}: {check_result['message']}")
        
        # Calculate summary
        passed_count = sum(1 for r in results if r["passed"] == True)
        failed_count = sum(1 for r in results if r["passed"] == False)
        unknown_count = sum(1 for r in results if r["passed"] is None)
        
        all_passed = failed_count == 0 and unknown_count == 0
        
        return {
            "all_passed": all_passed,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "unknown_count": unknown_count,
            "total_checks": len(checks),
            "results": results
        }
    
    def _validate_single_check(
        self,
        files: Dict[str, str],
        check: str
    ) -> Dict[str, Any]:
        """
        Validate a single check against generated files.
        
        Args:
            files: Dictionary of {filename: content}
            check: Single check string
        
        Returns:
            Dict with check validation result
        """
        check_lower = check.lower()
        
        # Try to import BeautifulSoup for HTML parsing (optional)
        try:
            from bs4 import BeautifulSoup
            has_bs4 = True
        except ImportError:
            has_bs4 = False
        
        # Check 1: MIT License
        if "mit license" in check_lower or ("mit" in check_lower and "license" in check_lower):
            if "LICENSE" in files:
                license_content = files["LICENSE"]
                if isinstance(license_content, bytes):
                    license_content = license_content.decode('utf-8', errors='ignore')
                
                if "mit" in license_content.lower():
                    return {
                        "check": check,
                        "passed": True,
                        "message": "MIT License found"
                    }
                else:
                    return {
                        "check": check,
                        "passed": False,
                        "message": "LICENSE exists but does not appear to be MIT"
                    }
            else:
                return {
                    "check": check,
                    "passed": False,
                    "message": "LICENSE file missing"
                }
        
        # Check 2: README.md quality
        if "readme" in check_lower and ("professional" in check_lower or "complete" in check_lower):
            if "README.md" in files:
                readme = files["README.md"]
                if isinstance(readme, bytes):
                    readme = readme.decode('utf-8', errors='ignore')
                
                has_headings = bool(re.search(r'^#+\s', readme, re.MULTILINE))
                has_content = len(readme) > 200
                has_sections = "##" in readme
                
                if has_headings and has_content and has_sections:
                    return {
                        "check": check,
                        "passed": True,
                        "message": f"README appears professional ({len(readme)} chars, has headings)"
                    }
                else:
                    issues = []
                    if not has_headings:
                        issues.append("no headings")
                    if not has_content:
                        issues.append(f"too short ({len(readme)} chars)")
                    if not has_sections:
                        issues.append("no sections")
                    
                    return {
                        "check": check,
                        "passed": False,
                        "message": f"README quality issues: {', '.join(issues)}"
                    }
            else:
                return {
                    "check": check,
                    "passed": False,
                    "message": "README.md missing"
                }
        
        # Check 3: Element with specific ID
        if "element" in check_lower and "id=" in check_lower:
            # Extract ID from check string
            # Examples: "Page has element with id='result'" or 'id="result"'
            id_match = re.search(r"id=['\"]([^'\"]+)['\"]", check)
            
            if id_match:
                required_id = id_match.group(1)
                
                if "index.html" in files:
                    html = files["index.html"]
                    if isinstance(html, bytes):
                        html = html.decode('utf-8', errors='ignore')
                    
                    # Method 1: Use BeautifulSoup if available
                    if has_bs4:
                        try:
                            soup = BeautifulSoup(html, "html.parser")
                            element = soup.find(id=required_id)
                            if element:
                                return {
                                    "check": check,
                                    "passed": True,
                                    "message": f"Element with id='{required_id}' found ({element.name} tag)"
                                }
                        except Exception as e:
                            logger.warning(f"BeautifulSoup parsing failed: {e}")
                    
                    # Method 2: Regex fallback
                    id_pattern = rf'id\s*=\s*["\']({re.escape(required_id)})["\']'
                    if re.search(id_pattern, html, re.IGNORECASE):
                        return {
                            "check": check,
                            "passed": True,
                            "message": f"Element with id='{required_id}' found (regex match)"
                        }
                    else:
                        return {
                            "check": check,
                            "passed": False,
                            "message": f"Element with id='{required_id}' NOT found in HTML"
                        }
                else:
                    return {
                        "check": check,
                        "passed": False,
                        "message": "index.html missing, cannot check for element"
                    }
            else:
                return {
                    "check": check,
                    "passed": None,
                    "message": "Could not extract ID from check string"
                }
        
        # Check 4: Bootstrap from CDN
        if "bootstrap" in check_lower and ("cdn" in check_lower or "load" in check_lower):
            if "index.html" in files:
                html = files["index.html"]
                if isinstance(html, bytes):
                    html = html.decode('utf-8', errors='ignore')
                
                # Check for common Bootstrap CDN links
                bootstrap_cdns = [
                    "cdn.jsdelivr.net/npm/bootstrap",
                    "stackpath.bootstrapcdn.com/bootstrap",
                    "maxcdn.bootstrapcdn.com/bootstrap",
                    "getbootstrap.com",
                    "bootstrap.min.css",
                    "bootstrap.min.js"
                ]
                
                found_cdn = any(cdn in html for cdn in bootstrap_cdns)
                
                if found_cdn:
                    # Check version if specified
                    if "5" in check_lower or "bootstrap 5" in check_lower:
                        if "/5." in html or "bootstrap@5" in html:
                            return {
                                "check": check,
                                "passed": True,
                                "message": "Bootstrap 5 CDN link found"
                            }
                        else:
                            return {
                                "check": check,
                                "passed": False,
                                "message": "Bootstrap found but version may not be 5"
                            }
                    else:
                        return {
                            "check": check,
                            "passed": True,
                            "message": "Bootstrap CDN link found"
                        }
                else:
                    return {
                        "check": check,
                        "passed": False,
                        "message": "No Bootstrap CDN link found in HTML"
                    }
            else:
                return {
                    "check": check,
                    "passed": False,
                    "message": "index.html missing"
                }
        
        # Check 5: Performs operations/calculations
        if any(word in check_lower for word in ["perform", "operation", "calculat", "arithmetic"]):
            code_to_check = ""
            
            # Combine HTML and JS
            if "index.html" in files:
                html = files["index.html"]
                if isinstance(html, bytes):
                    html = html.decode('utf-8', errors='ignore')
                code_to_check += html
            
            if "script.js" in files:
                js = files["script.js"]
                if isinstance(js, bytes):
                    js = js.decode('utf-8', errors='ignore')
                code_to_check += "\n" + js
            
            # Look for function definitions
            has_functions = bool(re.search(r'\bfunction\s+\w+\s*\(', code_to_check)) or \
                           "=>" in code_to_check or \
                           bool(re.search(r'\bconst\s+\w+\s*=\s*\(', code_to_check))
            
            # Look for arithmetic operators
            has_operators = any(op in code_to_check for op in [" + ", " - ", " * ", " / ", "+=", "-=", "*=", "/="])
            
            # Look for calculation-related keywords
            has_calc_keywords = any(word in code_to_check.lower() for word in ["calculate", "compute", "result", "sum", "total"])
            
            if has_functions and has_operators:
                return {
                    "check": check,
                    "passed": True,
                    "message": "Code contains functions and arithmetic operations"
                }
            elif has_operators and has_calc_keywords:
                return {
                    "check": check,
                    "passed": True,
                    "message": "Code contains arithmetic operations and calculation logic"
                }
            else:
                missing = []
                if not has_functions:
                    missing.append("no functions")
                if not has_operators:
                    missing.append("no arithmetic operators")
                
                return {
                    "check": check,
                    "passed": False,
                    "message": f"Code may not perform operations: {', '.join(missing)}"
                }
        
        # Check 6: Generic keyword matching (fallback)
        # For checks we can't parse programmatically, do basic keyword search
        if "index.html" in files:
            html = files["index.html"]
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='ignore')
            
            # Extract likely keywords from check
            keywords = re.findall(r'\b[a-zA-Z]{4,}\b', check_lower)
            keywords = [k for k in keywords if k not in ["page", "element", "have", "must", "should", "repo", "file"]]
            
            if keywords:
                found = sum(1 for kw in keywords if kw in html.lower())
                if found >= len(keywords) * 0.5:  # At least 50% keywords present
                    return {
                        "check": check,
                        "passed": None,
                        "message": f"Some keywords found, but cannot fully validate programmatically"
                    }
        
        # Default: Cannot validate programmatically
        return {
            "check": check,
            "passed": None,
            "message": "Cannot validate this check programmatically (manual review needed)"
        }
    
    def validate_deployed_page(
        self,
        pages_url: str,
        checks: List[str],
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Validate live deployed page.
        
        Args:
            pages_url: URL of deployed GitHub Pages site
            checks: List of checks to validate
            timeout: Request timeout in seconds
        
        Returns:
            Dict with validation results
        """
        logger.info(f"Validating deployed page: {pages_url}")
        
        errors = []
        warnings = []
        info = {}
        
        try:
            # Fetch the page
            response = httpx.get(
                pages_url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Validation Bot)"}
            )
            
            info["status_code"] = response.status_code
            info["response_time_ms"] = int(response.elapsed.total_seconds() * 1000)
            
            # Check response code
            if response.status_code != 200:
                errors.append(f"Page returned HTTP {response.status_code}")
                return {
                    "passed": False,
                    "errors": errors,
                    "warnings": warnings,
                    "info": info
                }
            
            html = response.text
            info["html_size_bytes"] = len(html)
            
            # Check page is not empty
            if len(html) < 100:
                errors.append(f"Page HTML is too short ({len(html)} bytes)")
            
            # Try to parse HTML if BeautifulSoup is available
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                
                # Count elements
                info["title"] = soup.title.string if soup.title else None
                info["scripts_count"] = len(soup.find_all("script"))
                info["links_count"] = len(soup.find_all("link"))
                
                # Check for obvious errors in text
                page_text = soup.get_text().lower()
                if "404" in page_text or "not found" in page_text:
                    warnings.append("Page text contains '404' or 'not found'")
                
                # Validate elements from checks
                for check in checks:
                    if "id=" in check.lower():
                        id_match = re.search(r"id=['\"]([^'\"]+)['\"]", check)
                        if id_match:
                            required_id = id_match.group(1)
                            element = soup.find(id=required_id)
                            if not element:
                                errors.append(f"Required element id='{required_id}' not found on live page")
                            else:
                                logger.info(f"  ✓ Element id='{required_id}' found on live page")
                    
                    # Check Bootstrap
                    if "bootstrap" in check.lower():
                        bootstrap_link = soup.find("link", href=lambda x: x and "bootstrap" in x)
                        if not bootstrap_link:
                            warnings.append("Bootstrap CSS link not found on live page")
                
            except ImportError:
                logger.warning("BeautifulSoup not available, skipping detailed HTML parsing")
            except Exception as e:
                warnings.append(f"HTML parsing error: {str(e)}")
            
            # Check for JS errors in HTML (basic)
            if "error" in html.lower() or "uncaught" in html.lower():
                warnings.append("Possible JavaScript errors detected in page source")
            
            result = {
                "passed": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "info": info
            }
            
            logger.info(f"Live page validation: {len(errors)} errors, {len(warnings)} warnings")
            return result
            
        except httpx.TimeoutException:
            errors.append(f"Page request timed out after {timeout}s")
        except httpx.RequestError as e:
            errors.append(f"Failed to fetch page: {str(e)}")
        except Exception as e:
            errors.append(f"Unexpected error: {str(e)}")
        
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
            "info": info
        }

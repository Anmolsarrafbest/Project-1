"""LLM-powered application generator using OpenAI."""
import logging
import base64
import json
from datetime import datetime
from openai import OpenAI
from typing import Dict, List
from models import Attachment

logger = logging.getLogger(__name__)


class LLMGenerator:
    """Generate web applications using LLM assistance."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = None):
        """Initialize OpenAI-compatible client (supports AI Pipe).

        This explicitly logs which endpoint is being used and ensures the
        base_url is passed to the OpenAI client when using AI Pipe.
        """
        # Store model early for use elsewhere
        self.model = model

        # Explicit behavior: if the base_url looks like AI Pipe, pass it
        if base_url and "aipipe" in base_url:
            logger.info(f"Using AI Pipe endpoint: {base_url}")
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            logger.info("Using standard OpenAI endpoint")
            # When base_url is None or not AI Pipe, use default OpenAI behavior
            if base_url:
                # If user supplied a non-AI-Pipe base_url, pass it through
                logger.info(f"Using custom base_url: {base_url}")
                self.client = OpenAI(api_key=api_key, base_url=base_url)
            else:
                self.client = OpenAI(api_key=api_key)
    
    def generate_app(
        self,
        brief: str,
        checks: List[str],
        attachments: List[Attachment],
        task_id: str,
        round_num: int,
        existing_files: Dict[str, str] = None
    ) -> Dict[str, str]:
        """
        Generate complete web application or update existing one.
        
        Args:
            brief: Task description (for Round 2, this is the UPDATE request)
            checks: Validation checks that will be performed
            attachments: File attachments
            task_id: Unique task identifier
            round_num: Round number (1 or 2)
            existing_files: For Round 2, the current repo files to update
        
        Returns:
            Dictionary of {filename: content}
        """
        logger.info(f"Generating app for task: {task_id} (round {round_num})")
        logger.info(f"Brief: {brief[:100]}...")
        
        if round_num > 1 and existing_files:
            logger.info(f"Round {round_num}: Updating existing app with {len(existing_files)} files")
            return self._update_existing_app(brief, checks, attachments, task_id, existing_files)
        else:
            logger.info("Round 1: Creating new app from scratch")
            return self._create_new_app(brief, checks, attachments, task_id, round_num)
    
    def _create_new_app(
        self,
        brief: str,
        checks: List[str],
        attachments: List[Attachment],
        task_id: str,
        round_num: int
    ) -> Dict[str, str]:
        """Create a new app from scratch (Round 1)."""
        # Build comprehensive prompt
        prompt = self._build_prompt(brief, checks, attachments, task_id, round_num)
        
        # Call LLM
        logger.info("Calling OpenAI API...")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        # Parse generated code
        files = self._parse_response(response.choices[0].message.content, attachments)
        
        # Add required files
        files["LICENSE"] = self._generate_mit_license()
        files["README.md"] = self._generate_readme(brief, task_id, files)
        
        logger.info(f"Generated {len(files)} files")
        return files
    
    def _update_existing_app(
        self,
        update_brief: str,
        checks: List[str],
        attachments: List[Attachment],
        task_id: str,
        existing_files: Dict[str, str]
    ) -> Dict[str, str]:
        """Update an existing app incrementally (Round 2+)."""
        logger.info("Building incremental update prompt with existing code...")
        
        # Build update prompt with existing code context
        prompt_parts = [
            f"**Task ID:** {task_id}",
            f"**Update Request:** {update_brief}",
            "\n**IMPORTANT:** This is an UPDATE to an existing application. You must:",
            "1. Read and understand the existing code below",
            "2. Make ONLY the changes needed to fulfill the new brief",
            "3. Preserve all existing functionality that still works",
            "4. Don't regenerate from scratch - incrementally improve",
            "\n**Existing Code:**\n"
        ]
        
        # Show existing files to LLM
        for filename, content in existing_files.items():
            if filename not in ["LICENSE", "README.md"]:  # Skip auto-generated files
                if isinstance(content, bytes):
                    prompt_parts.append(f"\n**{filename}** (binary file, {len(content)} bytes)")
                else:
                    preview = content[:3000] if len(content) > 3000 else content
                    prompt_parts.append(f"\n**{filename}:**\n```\n{preview}\n```")
        
        prompt_parts.append(f"\n**New Requirements (what to add/change):**\n{update_brief}")
        
        if checks:
            prompt_parts.append("\n**Validation Checks (app must still pass these):**")
            for i, check in enumerate(checks, 1):
                prompt_parts.append(f"{i}. {check}")
        
        if attachments:
            prompt_parts.append("\n**New Attachments:**")
            for att in attachments:
                if att.url.startswith("data:"):
                    try:
                        prompt_parts.append(self._decode_attachment_preview(att))
                    except Exception as e:
                        logger.warning(f"Could not decode {att.name}: {e}")
        
        prompt_parts.append("\n**Now update the application to include the new requirements while preserving existing features.**")
        
        prompt = "\n".join(prompt_parts)
        
        # Call LLM with update prompt
        logger.info("Calling OpenAI API for incremental update...")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self._get_update_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.5,  # Lower temperature for more conservative updates
            max_tokens=4000
        )
        
        # Parse updated code
        updated_files = self._parse_response(response.choices[0].message.content, attachments)
        
        # Merge: keep files that weren't modified
        final_files = existing_files.copy()
        final_files.update(updated_files)
        
        # Always regenerate README to reflect updates
        final_files["README.md"] = self._generate_readme(
            f"Original: {existing_files.get('README.md', 'N/A')}\n\nUpdate: {update_brief}",
            task_id,
            final_files
        )
        
        # Keep LICENSE unchanged
        if "LICENSE" not in final_files:
            final_files["LICENSE"] = self._generate_mit_license()
        
        logger.info(f"Updated app: {len(updated_files)} files modified, {len(final_files)} total files")
        return final_files
    
    def fix_validation_failures(
        self,
        files: Dict[str, str],
        failed_checks: List[Dict],
        task_id: str
    ) -> Dict[str, str]:
        """
        Quick targeted fixes for failed validation checks.
        Only regenerates files that need fixing, not the entire app.
        
        Args:
            files: Current files
            failed_checks: List of failed check results from validator
            task_id: Task ID for context
        
        Returns:
            Updated files (only changed files)
        """
        if not failed_checks:
            return files
        
        logger.info(f"Attempting targeted fixes for {len(failed_checks)} failed checks...")
        
        # Group failures by file to fix
        fixes_needed = {
            "README.md": [],
            "index.html": [],
            "other": []
        }
        
        for check in failed_checks:
            check_lower = check["check"].lower()
            
            if "readme" in check_lower:
                fixes_needed["README.md"].append(check)
            elif "element" in check_lower or "id=" in check_lower or "bootstrap" in check_lower:
                fixes_needed["index.html"].append(check)
            else:
                fixes_needed["other"].append(check)
        
        # Fix each file independently (faster than regenerating all)
        updated_files = files.copy()
        
        # Fix README.md
        if fixes_needed["README.md"]:
            logger.info("Fixing README.md...")
            updated_files["README.md"] = self._fix_readme(
                files.get("README.md", ""),
                fixes_needed["README.md"],
                task_id
            )
        
        # Fix index.html
        if fixes_needed["index.html"]:
            logger.info("Fixing index.html...")
            updated_files["index.html"] = self._fix_html(
                files.get("index.html", ""),
                fixes_needed["index.html"]
            )
        
        return updated_files
    
    def _fix_readme(
        self,
        current_readme: str,
        failed_checks: List[Dict],
        task_id: str
    ) -> str:
        """Fix README.md issues quickly."""
        issues = []
        for check in failed_checks:
            issues.append(f"- {check['check']}: {check['message']}")
        
        prompt = f"""Fix the README.md for task "{task_id}".

**Current README:**
```
{current_readme}
```

**Issues to fix:**
{chr(10).join(issues)}

**Requirements:**
- Make it professional and complete (at least 300 characters)
- Add proper markdown sections (## headings)
- Include: Project Summary, Features, Setup Instructions, Usage
- Keep it concise but informative
- Use proper markdown formatting

Return ONLY the fixed README.md content, no JSON, no code blocks."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a technical writer. Return only the README content."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            fixed_readme = response.choices[0].message.content.strip()
            
            # Remove markdown code fences if LLM added them
            if fixed_readme.startswith("```"):
                lines = fixed_readme.split("\n")
                fixed_readme = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            logger.info(f"README fixed: {len(current_readme)} → {len(fixed_readme)} chars")
            return fixed_readme
            
        except Exception as e:
            logger.error(f"Failed to fix README: {e}")
            return current_readme
    
    def _fix_html(
        self,
        current_html: str,
        failed_checks: List[Dict]
    ) -> str:
        """Fix HTML issues quickly (add missing elements, Bootstrap, etc)."""
        issues = []
        for check in failed_checks:
            issues.append(f"- {check['check']}: {check['message']}")
        
        prompt = f"""Fix the HTML below to pass these checks:

{chr(10).join(issues)}

**Current HTML:**
```html
{current_html}
```

**Fix requirements:**
- Add ONLY what's missing (don't rewrite everything)
- If element with specific id is missing, add it
- If Bootstrap CDN is missing, add the link in <head>
- Preserve existing functionality
- Return the complete fixed HTML

Return ONLY the fixed HTML, no explanation."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an HTML expert. Return only the fixed HTML code."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            fixed_html = response.choices[0].message.content.strip()
            
            # Remove markdown code fences
            if "```html" in fixed_html:
                import re
                match = re.search(r"```html\n(.*?)```", fixed_html, re.DOTALL)
                if match:
                    fixed_html = match.group(1).strip()
            elif fixed_html.startswith("```"):
                lines = fixed_html.split("\n")
                fixed_html = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            logger.info(f"HTML fixed: {len(current_html)} → {len(fixed_html)} chars")
            return fixed_html
            
        except Exception as e:
            logger.error(f"Failed to fix HTML: {e}")
            return current_html
    
    def _get_update_system_prompt(self) -> str:
        """System prompt for incremental updates."""
        return """You are an expert web developer specializing in maintaining and updating existing code.

Your task is to UPDATE an existing web application based on new requirements.

CRITICAL REQUIREMENTS FOR UPDATES:
1. READ the existing code carefully - understand what it does
2. Make MINIMAL changes to achieve the new requirements
3. PRESERVE all existing functionality that still works
4. Don't rewrite from scratch - update incrementally
5. Keep the same file structure unless adding new files is necessary
6. Maintain code style and patterns from the existing code
7. Add comments explaining what you changed and why

FUNCTIONALITY REQUIREMENTS (EXTREMELY IMPORTANT):
- Ensure ALL interactive elements continue to work after updates
- If adding new buttons/forms, they MUST have working event handlers
- Don't break existing event listeners when adding new ones
- Verify selectors still match after HTML changes
- Test mentally: "Will all features still work after this update?"

CODE QUALITY:
- Complete implementations only - no TODOs or placeholders
- Proper event handler attachment
- Correct DOM manipulation logic
- All user interactions must have responses

OUTPUT FORMAT:
Return ONLY the files that need to be modified or added as a JSON object:
{
  "files": {
    "index.html": "<!DOCTYPE html>\\n<html>...",
    "script.js": "// Updated script with new feature..."
  }
}

If a file doesn't need changes, DON'T include it in your response.
Return ONLY the JSON object, no other text.
CRITICAL: All new features must be fully implemented and working!"""
    
    def _get_system_prompt(self) -> str:
        """System prompt for code generation."""
        return """You are an expert web developer specializing in creating clean, working web applications.

Your task is to generate a complete, functional web application based on the user's requirements.

CRITICAL REQUIREMENTS:
1. Create working code that runs in a browser - ALL FEATURES MUST WORK
2. Use CDN links for any libraries (Bootstrap, jQuery, Chart.js, etc.)
3. Make the app professional and user-friendly
4. Follow the brief EXACTLY - implement all requirements
5. Ensure all validation checks will pass
6. Use modern, clean code with proper error handling
7. Add helpful comments explaining key logic

FUNCTIONALITY REQUIREMENTS (EXTREMELY IMPORTANT):
- ALL interactive elements (buttons, forms, inputs) MUST have working event handlers
- Event listeners must be properly attached using addEventListener or jQuery .on()/.click()
- Button clicks MUST perform actual actions (don't leave placeholder TODOs)
- Forms MUST handle submit events and prevent default behavior
- User input MUST be validated and processed correctly
- DOM manipulation MUST actually create/update/delete elements as intended
- Test mentally: "Will clicking this button actually do something?" - If no, FIX IT!

CODE QUALITY:
- Write complete implementations, not placeholders
- Include all necessary JavaScript logic
- Ensure event handlers are attached after DOM is ready
- Use proper selectors that match the HTML element IDs/classes
- Add console.log for debugging but ensure core logic is complete

OUTPUT FORMAT:
Return your response as a valid JSON object with this structure:
{
  "files": {
    "index.html": "<!DOCTYPE html>\\n<html>...",
    "style.css": "/* Optional separate CSS */",
    "script.js": "// Optional separate JS"
  }
}

If the app can fit in a single HTML file with embedded CSS/JS, that's fine - just include index.html.
If you need separate files for better organization, include style.css and/or script.js.

IMPORTANT: Return ONLY the JSON object, no other text.
CRITICAL: ALL interactive features must be fully implemented and working - no placeholders!"""
    
    def _build_prompt(
        self,
        brief: str,
        checks: List[str],
        attachments: List[Attachment],
        task_id: str,
        round_num: int
    ) -> str:
        """Build the user prompt with all context."""
        parts = [
            f"**Task ID:** {task_id}",
            f"**Round:** {round_num}",
            f"\n**Brief:**\n{brief}",
        ]
        
        if checks:
            parts.append("\n**Validation Checks (your app must pass these):**")
            for i, check in enumerate(checks, 1):
                parts.append(f"{i}. {check}")
        
        if attachments:
            parts.append("\n**Attachments:**")
            for att in attachments:
                # Decode and preview attachment content
                if att.url.startswith("data:"):
                    try:
                        parts.append(self._decode_attachment_preview(att))
                    except Exception as e:
                        logger.warning(f"Could not decode {att.name}: {e}")
                        parts.append(f"\n**{att.name}:** [Binary data]")
        
        parts.append("\n**Generate the complete web application now.**")
        
        return "\n".join(parts)
    
    def _decode_attachment_preview(self, attachment: Attachment) -> str:
        """Decode attachment and create preview for LLM context."""
        header, encoded = attachment.url.split(",", 1)
        content_type = header.split(";")[0].replace("data:", "")
        
        if "base64" in header:
            decoded = base64.b64decode(encoded)
            
            # If it's text-based, show preview
            if any(t in content_type for t in ["text", "json", "csv", "xml"]):
                text = decoded.decode("utf-8", errors="ignore")
                preview = text[:1000] if len(text) > 1000 else text
                return f"\n**{attachment.name}** ({content_type}):\n```\n{preview}\n```"
            else:
                return f"\n**{attachment.name}** ({content_type}): [Binary data, {len(decoded)} bytes]"
        else:
            return f"\n**{attachment.name}** ({content_type}):\n```\n{encoded[:500]}\n```"
    
    def _parse_response(
        self,
        response_text: str,
        attachments: List[Attachment]
    ) -> Dict[str, str]:
        """Parse LLM response and extract files."""
        files = {}
        
        try:
            # Extract JSON from response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = response_text[start:end]
                data = json.loads(json_str)
                
                if "files" in data:
                    files = data["files"]
                else:
                    files = data
                
                # Fix escaped newlines and quotes in file content
                # This handles cases where LLM returns improperly escaped content
                for filename, content in files.items():
                    if isinstance(content, str):
                        # First pass: handle double-escaped sequences from JSON
                        content = content.replace('\\n', '\n')
                        content = content.replace('\\t', '\t')
                        content = content.replace('\\r', '\r')
                        content = content.replace('\\"', '"')
                        content = content.replace("\\'", "'")
                        
                        # Second pass: detect and fix literal escape sequences
                        # If HTML/JS/CSS still contains literal \n or \" after JSON parsing,
                        # it means LLM returned them as raw text instead of proper escapes
                        if filename.endswith(('.html', '.htm', '.js', '.css', '.json')):
                            # Check if content still has problematic patterns
                            test_str = content[:500]  # Check first 500 chars
                            if '\\n' in test_str or '\\"' in test_str or '\\t' in test_str:
                                logger.warning(f"Detected literal escape sequences in {filename}, attempting to fix...")
                                try:
                                    # Try to decode unicode escape sequences
                                    content = content.encode('utf-8').decode('unicode_escape')
                                except Exception as e:
                                    logger.warning(f"Could not decode escape sequences in {filename}: {e}")
                        
                        files[filename] = content
            else:
                raise ValueError("No JSON found in response")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not parse JSON response: {e}")
            # Fallback: try to extract code blocks
            files = self._extract_code_blocks(response_text)
        
        # Save attachments as files (they might be referenced in the code)
        for att in attachments:
            if att.url.startswith("data:"):
                try:
                    header, encoded = att.url.split(",", 1)
                    if "base64" in header:
                        content = base64.b64decode(encoded)
                    else:
                        content = encoded.encode()
                    
                    files[att.name] = content
                except Exception as e:
                    logger.error(f"Error processing attachment {att.name}: {e}")
        
        return files
    
    def _extract_code_blocks(self, text: str) -> Dict[str, str]:
        """Fallback: extract code from markdown blocks."""
        import re
        files = {}
        
        # Try to find HTML
        html_match = re.search(r"```html\n(.*?)```", text, re.DOTALL)
        if html_match:
            files["index.html"] = html_match.group(1).strip()
        
        # Try to find CSS
        css_match = re.search(r"```css\n(.*?)```", text, re.DOTALL)
        if css_match:
            files["style.css"] = css_match.group(1).strip()
        
        # Try to find JavaScript
        js_match = re.search(r"```(?:javascript|js)\n(.*?)```", text, re.DOTALL)
        if js_match:
            files["script.js"] = js_match.group(1).strip()
        
        # If no structured blocks, look for any HTML
        if not files:
            html_match = re.search(
                r"<!DOCTYPE html>.*?</html>",
                text,
                re.DOTALL | re.IGNORECASE
            )
            if html_match:
                files["index.html"] = html_match.group(0)
        
        return files
    
    def _generate_mit_license(self) -> str:
        """Generate MIT License text."""
        year = datetime.now().year
        return f"""MIT License

Copyright (c) {year} Student Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    
    def _generate_readme(
        self,
        brief: str,
        task_id: str,
        files: Dict[str, str]
    ) -> str:
        """Generate comprehensive README."""
        file_list = "\n".join([
            f"- `{name}`" for name in sorted(files.keys())
            if name != "README.md"
        ])
        
        return f"""# {task_id}

## Project Summary

{brief}

**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

## Files

{file_list}

## Setup Instructions

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd {task_id}
   ```

2. Open in browser:
   - Simply open `index.html` in your web browser
   - Or use a local server:
     ```bash
     python -m http.server 8000
     # Visit http://localhost:8000
     ```

## Usage

Open the application in a modern web browser. The app will automatically handle the requirements as specified in the project brief.

## Code Explanation

### Main Components

- **index.html**: Main application interface and structure
- **style.css**: Styling and layout (if separate file)
- **script.js**: Application logic and interactivity (if separate file)

The application is built using standard web technologies (HTML5, CSS3, JavaScript) and may include external libraries loaded via CDN for additional functionality.

### Key Features

The application implements all requirements specified in the brief, with proper error handling and user-friendly interface design.

## Technical Details

- Pure client-side application (no backend required)
- External libraries loaded from CDN (no build process needed)
- Responsive design for various screen sizes
- Modern browser required (Chrome, Firefox, Safari, Edge)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Deployment

This application is deployed on GitHub Pages at the repository's Pages URL.
"""

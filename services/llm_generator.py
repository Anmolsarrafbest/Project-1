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
        round_num: int
    ) -> Dict[str, str]:
        """
        Generate complete web application.
        
        Args:
            brief: Task description
            checks: Validation checks that will be performed
            attachments: File attachments
            task_id: Unique task identifier
            round_num: Round number (1 or 2)
        
        Returns:
            Dictionary of {filename: content}
        """
        logger.info(f"Generating app for task: {task_id} (round {round_num})")
        logger.info(f"Brief: {brief[:100]}...")
        
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
    
    def _get_system_prompt(self) -> str:
        """System prompt for code generation."""
        return """You are an expert web developer specializing in creating clean, working web applications.

Your task is to generate a complete, functional web application based on the user's requirements.

CRITICAL REQUIREMENTS:
1. Create working code that runs in a browser
2. Use CDN links for any libraries (Bootstrap, jQuery, Chart.js, etc.)
3. Make the app professional and user-friendly
4. Follow the brief EXACTLY - implement all requirements
5. Ensure all validation checks will pass
6. Use modern, clean code with proper error handling
7. Add helpful comments explaining key logic

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

IMPORTANT: Return ONLY the JSON object, no other text."""
    
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

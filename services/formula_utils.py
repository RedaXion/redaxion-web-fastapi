"""
Formula Conversion Utilities

Converts LaTeX formulas to readable plain text for Word/PDF documents.
"""

import re


def latex_to_text(text: str) -> str:
    """
    Convert LaTeX math notation to readable plain text.
    
    Handles common LaTeX patterns like:
    - \\frac{a}{b} -> a/b
    - ^{2} -> ²
    - _{2} -> ₂
    - \\times -> ×
    - \\div -> ÷
    - \\( ... \\) -> removes delimiters
    - $ ... $ -> removes delimiters
    """
    if not text:
        return text
    
    result = text
    
    # Remove LaTeX math delimiters
    result = re.sub(r'\\\(', '', result)
    result = re.sub(r'\\\)', '', result)
    result = re.sub(r'\$\$', '', result)
    result = re.sub(r'\$', '', result)
    
    # Handle fractions: \frac{a}{b} -> (a/b)
    def replace_frac(match):
        num = match.group(1)
        den = match.group(2)
        return f"({num}/{den})"
    result = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', replace_frac, result)
    
    # Handle superscripts: ^{xyz} or ^x
    superscript_map = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
        'n': 'ⁿ', 'i': 'ⁱ', 'x': 'ˣ', 'y': 'ʸ'
    }
    
    def replace_superscript(match):
        content = match.group(1)
        return ''.join(superscript_map.get(c, c) for c in content)
    
    result = re.sub(r'\^\{([^}]+)\}', replace_superscript, result)
    result = re.sub(r'\^(\d)', lambda m: superscript_map.get(m.group(1), m.group(1)), result)
    
    # Handle subscripts: _{xyz} or _x
    subscript_map = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
        '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
        'a': 'ₐ', 'e': 'ₑ', 'o': 'ₒ', 'x': 'ₓ', 
        'i': 'ᵢ', 'j': 'ⱼ', 'n': 'ₙ', 'm': 'ₘ'
    }
    
    def replace_subscript(match):
        content = match.group(1)
        return ''.join(subscript_map.get(c, c) for c in content)
    
    result = re.sub(r'_\{([^}]+)\}', replace_subscript, result)
    result = re.sub(r'_(\d)', lambda m: subscript_map.get(m.group(1), m.group(1)), result)
    result = re.sub(r'_([a-z])', lambda m: subscript_map.get(m.group(1), m.group(1)), result)
    
    # Common operators and symbols
    replacements = [
        (r'\\times', '×'),
        (r'\\cdot', '·'),
        (r'\\div', '÷'),
        (r'\\pm', '±'),
        (r'\\mp', '∓'),
        (r'\\leq', '≤'),
        (r'\\geq', '≥'),
        (r'\\neq', '≠'),
        (r'\\approx', '≈'),
        (r'\\equiv', '≡'),
        (r'\\sim', '∼'),
        (r'\\propto', '∝'),
        (r'\\infty', '∞'),
        (r'\\sqrt\{([^}]+)\}', r'√(\1)'),
        (r'\\sqrt', '√'),
        (r'\\alpha', 'α'),
        (r'\\beta', 'β'),
        (r'\\gamma', 'γ'),
        (r'\\delta', 'δ'),
        (r'\\Delta', 'Δ'),
        (r'\\epsilon', 'ε'),
        (r'\\theta', 'θ'),
        (r'\\lambda', 'λ'),
        (r'\\mu', 'μ'),
        (r'\\pi', 'π'),
        (r'\\sigma', 'σ'),
        (r'\\Sigma', 'Σ'),
        (r'\\omega', 'ω'),
        (r'\\Omega', 'Ω'),
        (r'\\rho', 'ρ'),
        (r'\\phi', 'φ'),
        (r'\\psi', 'ψ'),
        (r'\\rightarrow', '→'),
        (r'\\leftarrow', '←'),
        (r'\\Rightarrow', '⇒'),
        (r'\\Leftarrow', '⇐'),
        (r'\\leftrightarrow', '↔'),
        (r'\\partial', '∂'),
        (r'\\nabla', '∇'),
        (r'\\int', '∫'),
        (r'\\sum', 'Σ'),
        (r'\\prod', '∏'),
        (r'\\forall', '∀'),
        (r'\\exists', '∃'),
        (r'\\in', '∈'),
        (r'\\notin', '∉'),
        (r'\\subset', '⊂'),
        (r'\\supset', '⊃'),
        (r'\\cup', '∪'),
        (r'\\cap', '∩'),
        (r'\\emptyset', '∅'),
        (r'\\degree', '°'),
        (r'\\circ', '°'),
        (r'\\text\{([^}]+)\}', r'\1'),  # Remove \text{} wrapper
        (r'\\mathrm\{([^}]+)\}', r'\1'),  # Remove \mathrm{} wrapper
        (r'\\,', ' '),  # Thin space
        (r'\\;', ' '),  # Medium space
        (r'\\:', ' '),  # Medium space
        (r'\\ ', ' '),  # Space
        (r'\\quad', '  '),  # Quad space
        (r'\\qquad', '    '),  # Double quad space
        (r'\\left', ''),
        (r'\\right', ''),
        (r'\\big', ''),
        (r'\\Big', ''),
        (r'\\bigg', ''),
        (r'\\Bigg', ''),
    ]
    
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)
    
    # Clean up any remaining backslashes before common words
    result = re.sub(r'\\([a-zA-Z]+)', r'\1', result)
    
    # Clean up extra whitespace
    result = re.sub(r'\s+', ' ', result)
    
    return result.strip()


def process_text_formulas(text: str) -> str:
    """
    Process an entire text block, converting any LaTeX formulas found.
    """
    if not text:
        return text
    
    # Convert LaTeX delimited content
    result = latex_to_text(text)
    
    return result

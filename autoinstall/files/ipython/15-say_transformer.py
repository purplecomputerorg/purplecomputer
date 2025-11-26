"""
Purple Computer - Say Input Transformer
Allows kids to type 'say hello' instead of 'say("hello")'
"""

import re


def say_transformer(lines):
    """
    Transform 'say word word word' into 'say("word word word")'
    This lets kids type naturally without quotes or parens.
    """
    if not lines:
        return lines

    line = lines[0]

    # Match: say followed by words (but not already with parens)
    match = re.match(r'^say\s+(.+?)(?:\s*#.*)?$', line.strip())

    if match:
        words = match.group(1).strip()
        # Skip if already has parens (like say("hello"))
        if not (words.startswith('(') or words.startswith('"') or words.startswith("'")):
            return [f'say("{words}")']

    return lines


# Install the transformer
try:
    from IPython import get_ipython
    ip = get_ipython()
    if ip:
        ip.input_transformers_post.append(say_transformer)
except:
    pass

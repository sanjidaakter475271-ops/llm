import re

def validate_letter_json(letter_json):
    """
    Validates structured JSON output from AI:
    - Normalizes references (removes duplicate 'Ref: A. Ref: A.' errors)
    - Validates mandatory fields
    - Cleans subject formatting
    - Ensures body structure is correct
    """
    errors = []
    warnings = []
    
    # Check letter type
    valid_types = ['rl', 'lm', 'dl', 'fl', 'do', 'cl', 'mem']
    if letter_json.get('type') not in valid_types:
        errors.append(f"Invalid letter type: {letter_json.get('type')}")

    # Validate & normalize subject
    subj = letter_json.get('subject', '').strip()
    if not subj:
        errors.append("Subject is missing.")
    else:
        letter_json['subject'] = subj.upper()

    # Validate & normalize references
    refs = letter_json.get('refs', [])
    cleaned_refs = []
    for r in refs:
        if isinstance(r, str):
            # Clean duplicate prefixes
            clean_r = re.sub(r'^(refs?[:\s]*)+', '', r, flags=re.IGNORECASE).strip()
            clean_r = re.sub(r'^[A-Z]\.\s*', '', clean_r).strip()
            if clean_r and clean_r not in cleaned_refs:
                cleaned_refs.append(clean_r)
    letter_json['refs'] = cleaned_refs

    # Validate body
    body = letter_json.get('body', [])
    if not body or not isinstance(body, list):
        errors.append("Body must be a non-empty list.")
    else:
        # Check ending paragraph convention if required
        last_para = body[-1]
        last_text = last_para if isinstance(last_para, str) else last_para.get('text', '')
        if "info and nec act" not in last_text.lower():
            warnings.append("Last paragraph does not follow standard BAF ending phrase.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized_json": letter_json
    }

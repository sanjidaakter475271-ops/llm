import os
import json
import logging

TYPES = ["LM", "RL", "DL", "FL", "DO", "CL", "MEM"]
DATASET_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset")
TRAINING_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training")

def init_dataset_structure():
    for t in TYPES:
        os.makedirs(os.path.join(DATASET_BASE, t), exist_ok=True)
    os.makedirs(TRAINING_BASE, exist_ok=True)

def process_raw_letter(doc_id, letter_type, subject, references, body_paragraphs, metadata=None):
    init_dataset_structure()
    letter_type_upper = letter_type.upper()
    if letter_type_upper not in TYPES:
        letter_type_upper = "RL"
        
    structured_doc = {
        "id": doc_id,
        "type": letter_type_upper,
        "subject": subject,
        "references": references or [],
        "body": body_paragraphs or [],
        "metadata": metadata or {"quality": 5, "approved": True}
    }
    
    out_path = os.path.join(DATASET_BASE, letter_type_upper, f"{doc_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(structured_doc, f, indent=2, ensure_ascii=False)
        
    logging.info(f"Saved processed letter {doc_id} to {out_path}")
    return structured_doc

def build_training_jsonl():
    init_dataset_structure()
    approved_file = os.path.join(TRAINING_BASE, "approved_letters.jsonl")
    
    records = []
    for t in TYPES:
        type_dir = os.path.join(DATASET_BASE, t)
        if not os.path.exists(type_dir):
            continue
        for fname in os.listdir(type_dir):
            if fname.endswith(".json"):
                with open(os.path.join(type_dir, fname), "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    if doc.get("metadata", {}).get("approved", True):
                        records.append(doc)
                        
    with open(approved_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    logging.info(f"Built training JSONL with {len(records)} records at {approved_file}")
    return approved_file

if __name__ == "__main__":
    init_dataset_structure()
    print("Dataset directory structure initialized.")

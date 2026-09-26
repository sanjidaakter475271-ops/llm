import os
import json
import re

DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset")

def retrieve_similar_letters(query, letter_type=None, top_k=3):
    matches = []
    if not os.path.exists(DATASET_DIR):
        return matches

    query_words = set(re.findall(r'\w+', query.lower()))
    
    subdirs = [letter_type.upper()] if letter_type and os.path.exists(os.path.join(DATASET_DIR, letter_type.upper())) else os.listdir(DATASET_DIR)
    
    for folder in subdirs:
        folder_path = os.path.join(DATASET_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        for fname in os.listdir(folder_path):
            if fname.endswith(".json"):
                fpath = os.path.join(folder_path, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    
                text_to_search = f"{doc.get('subject', '')} {' '.join(doc.get('body', []))}".lower()
                doc_words = set(re.findall(r'\w+', text_to_search))
                
                score = len(query_words.intersection(doc_words))
                if score > 0 or not query_words:
                    matches.append((score, doc))
                    
    matches.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in matches[:top_k]]

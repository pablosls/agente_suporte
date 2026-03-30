import glob
import json
import time
import os
from docling.document_converter import DocumentConverter

def extract_images():
    img_dir = "ilovepdf_pages-to-jpg"
    files = sorted(glob.glob(os.path.join(img_dir, "*.jpg")))
    
    if not files:
        print(f"No JPG files found in {img_dir}.")
        return

    print(f"Found {len(files)} images to process using Docling OCR...")
    start = time.time()
    converter = DocumentConverter()
    
    all_docs = []
    
    for idx, file_path in enumerate(files):
        print(f"Processing ({idx+1}/{len(files)}): {file_path}...")
        try:
            res = converter.convert(file_path)
            all_docs.append({
                "source_image": file_path,
                "text": res.document.export_to_markdown()
            })
        except Exception as e:
            print(f"Failed processing {file_path}: {e}")
            
    output_json = "geladeira_images_extracted.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)
        
    elapsed = time.time() - start
    print(f"\nExtraction completed successfully!")
    print(f"Total time: {elapsed:.2f} seconds.")
    print(f"Results saved to: {output_json}")

if __name__ == "__main__":
    extract_images()

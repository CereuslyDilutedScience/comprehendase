from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import time
import shutil

from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
import ontology

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://cereuslydilutedscience.github.io"}})

UPLOAD_FOLDER = "uploads"
STATIC_PAGE_FOLDER = "static/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)

CLOUD_RUN_BASE = "https://comprehendase-backend-470914920668.us-east4.run.app"


# ---------------------------------------------------------
# Serve rendered page images
# ---------------------------------------------------------
@app.route("/static/pages/<path:filename>")
def serve_page_image(filename):
    return send_from_directory(STATIC_PAGE_FOLDER, filename)


# ---------------------------------------------------------
# Cleanup old rendered folders (default: 2 hours)
# ---------------------------------------------------------
def cleanup_old_render_folders(base_folder="static/pages", max_age_minutes=120):
    now = time.time()
    max_age_seconds = max_age_minutes * 60

    for name in os.listdir(base_folder):
        folder_path = os.path.join(base_folder, name)

        if os.path.isdir(folder_path):
            folder_age = now - os.path.getmtime(folder_path)

            if folder_age > max_age_seconds:
                print(f"Cleaning up old folder: {folder_path}")
                shutil.rmtree(folder_path, ignore_errors=True)


# ---------------------------------------------------------
# Main extraction endpoint
# ---------------------------------------------------------
@app.route("/extract", methods=["POST", "OPTIONS"])
def extract():
    if request.method == "OPTIONS":
        return '', 204

    start_time = time.time()
    print("Received request")

    # Validate upload
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)

    print(f"Saved file: {filename}")

    # -----------------------------------------------------
    # 1. Extract layout + get OCR-cleaned PDF path
    # -----------------------------------------------------
    cleaned_pdf, pages = extract_pdf_layout(filepath)
    print(f"Extraction complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 2. Render images from the SAME PDF used for extraction
    # -----------------------------------------------------
    image_paths = render_pdf_pages(cleaned_pdf, output_folder=STATIC_PAGE_FOLDER)
    print(f"Rendering complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 3. Run ontology lookup (FIX APPLIED HERE)
    # -----------------------------------------------------
    candidate_terms = ontology.extract_ontology_terms(pages)
    ontology_hits = ontology.process_terms(candidate_terms)
    print(f"Ontology lookup complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 4. Attach ontology hits + image URLs
    # -----------------------------------------------------
    for page_index, page in enumerate(pages):

        # Words
        for w in page["words"]:
            key = w["text"].lower().strip()
            if key in ontology_hits:
                w["term"] = ontology_hits[key]["label"]
                w["definition"] = ontology_hits[key]["definition"]

        # Phrases
        for phrase_obj in page["phrases"]:
            key = phrase_obj["text"].lower().strip()
            if key in ontology_hits:
                first_word = phrase_obj["words"][0]
                first_word["term"] = ontology_hits[key]["label"]
                first_word["definition"] = ontology_hits[key]["definition"]

                # Mark remaining words as skip
                for w in phrase_obj["words"][1:]:
                    w["skip"] = True

        # Add image URL
        page["image_url"] = f"{CLOUD_RUN_BASE}/{image_paths[page_index]}"

    # -----------------------------------------------------
    # 5. Cleanup old folders (2-hour retention)
    # -----------------------------------------------------
    cleanup_old_render_folders()

    print(f"Finished all processing — {time.time() - start_time:.2f}s")
    return jsonify({"pages": pages})


# ---------------------------------------------------------
# Run locally
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

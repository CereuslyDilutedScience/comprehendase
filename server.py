from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import time

from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
import ontology

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://cereuslydilutedscience.github.io"}})

UPLOAD_FOLDER = "uploads"
STATIC_PAGE_FOLDER = "/tmp/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)

CLOUD_RUN_BASE = "https://comprehendase-backend-470914920668.us-east4.run.app"


# ---------------------------------------------------------
# Serve rendered page images
# ---------------------------------------------------------
@app.route("/static/pages/<path:filename>")
def serve_page_image(filename):
    return send_from_directory("/tmp/pages", filename)


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
    # 1. Extract layout (GLOBAL words + phrases)
    # -----------------------------------------------------
    target_pdf, extracted = extract_pdf_layout(filepath)
    pages_meta = extracted["pages"]
    all_words = extracted["words"]
    all_phrases = extracted["phrases"]

    print(f"Extraction complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 2. Render images from the SAME PDF used for extraction
    # -----------------------------------------------------
    render_result = render_pdf_pages(target_pdf, output_folder=STATIC_PAGE_FOLDER)
    image_folder = render_result["folder"]
    image_list = render_result["images"]  # [{page, path}, ...]

    print(f"Rendering complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 3. Ontology lookup on GLOBAL phrases
    # -----------------------------------------------------
    candidate_terms = ontology.extract_ontology_terms({
        "words": all_words,
        "phrases": all_phrases
    })

    ontology_hits = ontology.process_terms(candidate_terms)

    print(f"Ontology lookup complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 4. Attach ontology hits to words + phrases
    # -----------------------------------------------------
    for w in all_words:
        key = w["text"].lower().strip()
        if key in ontology_hits:
            w["term"] = ontology_hits[key]["label"]
            w["definition"] = ontology_hits[key]["definition"]

    for phrase_obj in all_phrases:
        key = phrase_obj["text"].lower().strip()
        if key in ontology_hits:
            first_word = phrase_obj["words"][0]
            first_word["term"] = ontology_hits[key]["label"]
            first_word["definition"] = ontology_hits[key]["definition"]

            for w in phrase_obj["words"][1:]:
                w["skip"] = True

    # -----------------------------------------------------
    # 5. Attach image URLs to page metadata
    # -----------------------------------------------------
    for page in pages_meta:
        page_number = page["page_number"]

        match = next((img for img in image_list if img["page"] == page_number), None)
        if match:
            page["image_url"] = f"{CLOUD_RUN_BASE}/{match['path']}"
        else:
            page["image_url"] = None

    # -----------------------------------------------------
    # 6. Return unified output
    # -----------------------------------------------------
    print(f"Finished all processing — {time.time() - start_time:.2f}s")

    return jsonify({
        "pages": pages_meta,
        "words": all_words,
        "phrases": all_phrases
    })


# ---------------------------------------------------------
# Run locally
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

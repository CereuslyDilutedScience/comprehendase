from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import time

from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
import ontology   # <-- full module import

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://cereuslydilutedscience.github.io"}})

# Allow up to 50 MB uploads
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

UPLOAD_FOLDER = "uploads"
STATIC_PAGE_FOLDER = "static/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)

# Base URL of your Cloud Run service
CLOUD_RUN_BASE = "https://comprehendase-backend-470914920668.us-east4.run.app"

# Serve rendered page images
@app.route("/static/pages/<path:filename>")
def serve_page_image(filename):
    return send_from_directory(STATIC_PAGE_FOLDER, filename)


@app.route("/extract", methods=["POST", "OPTIONS"])
def extract():
    if request.method == "OPTIONS":
        return '', 204

    start_time = time.time()
    print("Received request")

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)
    print(f"Saved file: {filename} — {time.time() - start_time:.2f}s")

    # 1. Extract layout (words + phrases)
    pages = extract_pdf_layout(filepath)
    print(f"Extracted layout — {time.time() - start_time:.2f}s")

    # 2. Render page images
    image_paths = render_pdf_pages(filepath, output_folder=STATIC_PAGE_FOLDER)
    print(f"Rendered pages — {time.time() - start_time:.2f}s")

    # 3. Run ontology on the whole document
    ontology_hits = ontology.extract_ontology_terms(pages)   # <-- FIXED
    print(f"Ontology lookup complete — {time.time() - start_time:.2f}s")

    # 4. Attach ontology results to pages
    for page_index, page in enumerate(pages):

        # Attach single-word hits
        for w in page["words"]:
            text = w["text"]
            if text in ontology_hits:
                w["term"] = ontology_hits[text]["label"]
                w["definition"] = ontology_hits[text]["definition"]

        # Attach phrase hits
        for phrase_obj in page["phrases"]:
            phrase = phrase_obj["text"]
            if phrase in ontology_hits:
                first_word = phrase_obj["words"][0]
                first_word["term"] = ontology_hits[phrase]["label"]
                first_word["definition"] = ontology_hits[phrase]["definition"]

                # Mark remaining words as skip
                for w in phrase_obj["words"][1:]:
                    w["skip"] = True

        # Add image URL
        page["image_url"] = f"{CLOUD_RUN_BASE}/{image_paths[page_index]}"

    print(f"Finished all processing — {time.time() - start_time:.2f}s")
    return jsonify({"pages": pages})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

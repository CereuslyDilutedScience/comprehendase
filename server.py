from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import time
from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
import ontology
from debug_tools import DEBUG

# Uncomment this to globally enable debug collection.
# You can also call DEBUG.enable() conditionally if you prefer.
DEBUG.enable()


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

    # If you prefer per-request control, you can enable here instead:
    # DEBUG.enable()

    DEBUG.add_flow("request_received")

    start_time = time.time()
    print("Received request")

    # Validate upload
    if "file" not in request.files:
        DEBUG.add_flow("no_file_in_request")
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)

    DEBUG.add_flow(f"file_saved:{filename}")
    print(f"Saved file: {filename}")

    # -----------------------------------------------------
    # 1. Extract layout (GLOBAL words + phrases)
    # -----------------------------------------------------
    DEBUG.add_flow("layout_extraction_started")
    render_result = render_pdf_pages(filepath)
    render_metadata = render_result["images"]

    target_pdf, extracted = extract_pdf_layout(filepath, render_metadata)
    pages_meta = extracted["pages"]
    all_words = extracted["words"]
    all_phrases = extracted["phrases"]

    DEBUG.add_flow("layout_extraction_completed")
    print(f"Extraction complete — {time.time() - start_time:.2f}s")

    # Set counts after extraction
    DEBUG.set_count("pages", len(pages_meta))
    DEBUG.set_count("words", len(all_words))
    DEBUG.set_count("phrases", len(all_phrases))

    # Sample words and phrases (first few only)
    for w in all_words[:5]:
        DEBUG.add_sample("words", w)

    for p in all_phrases[:5]:
        DEBUG.add_sample("phrases", p)

    # Use pages_meta as a proxy for page-level / box-like info
    for page in pages_meta[:5]:
        DEBUG.add_sample("boxes", page)

    # -----------------------------------------------------
    # 2. Render images from the SAME PDF used for extraction
    # -----------------------------------------------------
    DEBUG.add_flow("page_rendering_started")
    render_result = render_pdf_pages(target_pdf, output_folder=STATIC_PAGE_FOLDER)
    image_folder = render_result["folder"]
    image_list = render_result["images"]

    DEBUG.add_flow("page_rendering_completed")
    print(f"Rendering complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 3. Ontology lookup (Phase‑1 pipeline)
    # -----------------------------------------------------
    DEBUG.add_flow("ontology_lookup_started")
    unified_hits = ontology.extract_ontology_terms({
        "words": all_words,
        "phrases": all_phrases
    })
    DEBUG.add_flow("ontology_lookup_completed")

    print(f"Ontology lookup complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 4. Attach definitions to phrases and words
    # -----------------------------------------------------

    # PHRASE LOOP — only phrase-level hits
    for phrase_obj in all_phrases:
        phrase_text = phrase_obj["text"].strip()
        hit = unified_hits.get(phrase_text)

        if not hit:
            continue

        source = hit.get("source")

        # PHRASE DEFINITIONS (internal or BioPortal)
        if source in ("phrase_definition", "ontology_phrase"):
            definition = hit.get("definition")
            if definition:
                for w in phrase_obj["words"]:
                    w["definition"] = definition
                    w["source"] = source

        # No other phrase-level cases exist in Phase‑1

    # WORD LOOP — apply word-level hits
    for w in all_words:
        word_text = w["text"].strip()
        hit = unified_hits.get(word_text)

        if not hit:
            continue

        source = hit.get("source")

        if source in ("word_definition", "ontology_word"):
            definition = hit.get("definition")
            if definition:
                w["definition"] = definition
                w["source"] = source

    DEBUG.add_flow("definitions_attached")

    # Count how many words ended up with definitions
    definitions_count = sum(1 for w in all_words if "definition" in w)
    DEBUG.set_count("definitions", definitions_count)

    # Sample a few words that actually have definitions
    words_with_def = [w for w in all_words if "definition" in w][:5]
    for w in words_with_def:
        DEBUG.add_sample("definitions", w)

    # -----------------------------------------------------
    # 5. Attach image URLs
    # -----------------------------------------------------
    DEBUG.add_flow("image_url_attachment_started")
    for page in pages_meta:
        page_number = page["page_number"]
        match = next((img for img in image_list if img["page"] == page_number), None)

        if match:
            page["image_url"] = f"{CLOUD_RUN_BASE}/{match['path']}"
        else:
            page["image_url"] = None

    DEBUG.add_flow("image_url_attachment_completed")

    # -----------------------------------------------------
    # 6. Return unified output
    # -----------------------------------------------------
    DEBUG.add_flow("response_ready")
    print(f"Finished all processing — {time.time() - start_time:.2f}s")

    # Emit a single consolidated debug report (if enabled)
    report = DEBUG.emit()
    if report:
        print(report)

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

import os
import tempfile
import fitz  # PyMuPDF

def render_pdf_pages(pdf_path, output_folder="/tmp/pages", dpi=150):
    """
    Render each page of the PDF as a PNG image using PyMuPDF (fitz).
    Returns metadata including rendered image dimensions
    so extraction can scale coordinates correctly.
    """

    # Create a unique subfolder for this request
    unique_folder = next(tempfile._get_candidate_names())
    request_folder = os.path.join(output_folder, unique_folder)
    os.makedirs(request_folder, exist_ok=True)

    # Open PDF
    doc = fitz.open(pdf_path)

    # DPI → zoom factor
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    images = []

    for i, page in enumerate(doc):
        page_number = i + 1

        try:
            # Render page
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Debug info (safe)
            print(f"[RENDER DEBUG] Page {page_number}")
            print(f"  PyMuPDF page rect: width={page.rect.width}, height={page.rect.height}")
            print(f"  Rendered PNG size: width={pix.width}, height={pix.height}")

            # Save PNG
            filename = f"page_{page_number}.png"
            filepath = os.path.join(request_folder, filename)
            pix.save(filepath)

            # IMPORTANT: include rendered dimensions for extraction scaling
            images.append({
                "page": page_number,
                "path": f"static/pages/{unique_folder}/{filename}",
                "rendered_width": pix.width,
                "rendered_height": pix.height,
                "pdf_width": page.rect.width,
                "pdf_height": page.rect.height
            })

        except Exception as e:
            print(f"Error rendering page {page_number}: {e}", flush=True)
            continue

    return {
        "folder": unique_folder,
        "images": images
    }

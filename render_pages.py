import os
from pdf2image import convert_from_path

def render_pdf_pages(pdf_path, output_folder="static/pages", dpi=150):
    """
    Render each page of the PDF as a PNG image.
    Returns a list of file paths to the rendered images.
    """

    # Ensure output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Convert PDF pages to PIL images
    pages = convert_from_path(pdf_path, dpi=dpi)

    image_paths = []

    for i, page in enumerate(pages):
        filename = f"page_{i+1}.png"
        filepath = os.path.join(output_folder, filename)

        # Save page as PNG
        page.save(filepath, "PNG")

        image_paths.append(filepath)

    return image_paths

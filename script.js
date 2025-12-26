console.log("script.js updated");

// Set your backend URL here once Cloud Run is deployed
const BACKEND_URL = "https://comprehendase-252233072700.us-east4.run.app";

// Enable the button when a file is selected
document.getElementById("pdf-input").addEventListener("change", () => {
    const fileInput = document.getElementById("pdf-input");
    const button = document.getElementById("process-btn");

    button.disabled = fileInput.files.length === 0;
});

// Handle the "Reconstruct layout" button click
document.getElementById("process-btn").addEventListener("click", async () => {
    const fileInput = document.getElementById("pdf-input");
    const logBox = document.getElementById("log");
    const viewer = document.getElementById("page-viewer");
    const output = document.getElementById("output");

    if (!fileInput.files.length) {
        alert("Please upload a PDF first.");
        return;
    }

    logBox.textContent = "Uploading PDF and processing…";

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const response = await fetch(`${BACKEND_URL}/extract`, {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (data.error) {
            logBox.textContent = "Error: " + data.error;
            return;
        }

        logBox.textContent = "Rendering pages…";

        // Clear old content
        viewer.innerHTML = "";
        output.innerHTML = "";

        renderPages(data.pages, viewer);

        logBox.textContent = "Done.";

    } catch (err) {
        logBox.textContent = "Error contacting backend.";
        console.error(err);
    }
});

// Render pages + overlay text
function renderPages(pages, viewer) {
    pages.forEach((page) => {
        const pageWrapper = document.createElement("div");
        pageWrapper.className = "page-wrapper";

        // Page image
        const img = document.createElement("img");
        img.src = page.image_url;
        img.className = "page-image";

        // Overlay container
        const overlay = document.createElement("div");
        overlay.className = "text-overlay";

        img.onload = () => {
            const scaleX = img.clientWidth / page.width;
            const scaleY = img.clientHeight / page.height;

            page.words.forEach((word) => {
                if (word.skip) return;

                const span = document.createElement("span");
                span.className = "word";
                span.textContent = word.term || word.text;

                if (word.definition) {
                    span.classList.add("has-definition");
                    span.title = word.definition;
                }

                span.style.left = (word.x * scaleX) + "px";
                span.style.top = (word.y * scaleY) + "px";
                span.style.fontSize = (word.height * scaleY) + "px";

                overlay.appendChild(span);
            });
        };

        pageWrapper.appendChild(img);
        pageWrapper.appendChild(overlay);
        viewer.appendChild(pageWrapper);
    });
}

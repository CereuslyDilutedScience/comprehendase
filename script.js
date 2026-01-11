console.log("script.js updated");

// Set your backend URL here once Cloud Run is deployed
const BACKEND_URL = "https://comprehendase-backend-470914920668.us-east4.run.app";

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

        // NEW: pass global words + pages
        renderPages(data.pages, data.words, viewer);

        logBox.textContent = "Done.";

    } catch (err) {
        logBox.textContent = "Error contacting backend.";
        console.error(err);
    }
});

// Render pages + overlay text
function renderPages(pages, allWords, viewer) {
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
        overlay.style.width = img.clientWidth + "px";
        overlay.style.height = img.clientHeight + "px";

        const wordsOnPage = allWords.filter(w => w.page === page.page_number);

        wordsOnPage.forEach((word) => {
            if (word.skip) return;

            const span = document.createElement("span");
            span.className = "word";

            span.textContent = word.text;
            span.style.color = "transparent";

            if (word.definition) {
                span.classList.add("has-definition");
                span.title = word.definition;
        }

        // Use backend-scaled coordinates directly
            span.style.left = word.x + "px";
            span.style.top  = word.y + "px";

        // Use backend-scaled height directly
            span.style.fontSize = word.height + "px";
            span.style.lineHeight = word.height + "px";

            overlay.appendChild(span);
    });
};

        pageWrapper.appendChild(img);
        pageWrapper.appendChild(overlay);
        viewer.appendChild(pageWrapper);
    });
}

console.log("script.js updated");

const BACKEND_URL = "https://comprehendase-backend-470914920668.us-east4.run.app";

// ENABLE UPLOAD ONLY WHEN FILE IS SELECTED 
document.getElementById("pdf-input").addEventListener("change", () => {
    const fileInput = document.getElementById("pdf-input");
    const button = document.getElementById("process-btn");

    button.disabled = fileInput.files.length === 0;
});

// RECONSTRUCT LAYOUT BUTTON 
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

        // CLEAR OLD CONTENT
        viewer.innerHTML = "";
        output.innerHTML = "";

        // PASS GLOBAL WORDS + PAGES 
        renderPages(data.pages, data.words, viewer);

        logBox.textContent = "Done.";

    } catch (err) {
        logBox.textContent = "Error contacting backend.";
        console.error(err);
    }
});

// RENDER PAGES + OVERLAY TEXT
function renderPages(pages, allWords, viewer) {
    pages.forEach((page) => {
        const pageWrapper = document.createElement("div");
        pageWrapper.className = "page-wrapper";

        // PAGE IMAGE
        const img = document.createElement("img");
        img.src = page.image_url;
        img.className = "page-image";

        // OVERLAY CONTAINER
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

        // BACKEND-SCALED COORDINATES 
            span.style.left = word.x + "px";
            span.style.top  = word.y + "px";

        // BACKEND-SCALED HEIGHT
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

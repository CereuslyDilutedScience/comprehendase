console.log("script.js loaded");

// ------------------------------
// Backend URL
// ------------------------------
const BACKEND_URL = "https://comprehendase-252233072700.us-east4.run.app";

// ------------------------------
// Helpers: Logging + Progress Bar
// ------------------------------
function log(message) {
    const box = document.getElementById("logBox");
    box.textContent += "\n" + message;
    box.scrollTop = box.scrollHeight;
}

function setProgress(percent) {
    document.getElementById("progressBar").style.width = percent + "%";
}

// ------------------------------
// Upload Form Handler
// ------------------------------
document.getElementById("uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const fileInput = document.getElementById("pdfFile");
    if (!fileInput.files.length) {
        alert("Please upload a PDF first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    // Reset UI
    document.getElementById("output").innerHTML = "";
    document.getElementById("logBox").textContent = "Starting…";
    setProgress(5);

    log("Uploading PDF…");
    setProgress(15);

    try {
        const response = await fetch(`${BACKEND_URL}/extract`, {
            method: "POST",
            body: formData
        });

        log("Processing on server…");
        setProgress(40);

        const data = await response.json();

        if (data.error) {
            log("Error: " + data.error);
            setProgress(0);
            return;
        }

        log("Rendering pages…");
        setProgress(70);

        renderPages(data.pages);

        log("Done.");
        setProgress(100);

    } catch (err) {
        log("Error contacting backend.");
        console.error(err);
        setProgress(0);
    }
});

// ------------------------------
// Render Pages + Overlays
// ------------------------------
function renderPages(pages) {
    const output = document.getElementById("output");
    output.innerHTML = "";

    pages.forEach((page) => {
        const wrapper = document.createElement("div");
        wrapper.className = "page-wrapper";

        // Page image
        const img = document.createElement("img");
        img.className = "page-image";
        img.src = page.image_url;

        // Overlay container
        const overlay = document.createElement("div");
        overlay.className = "text-overlay";

        wrapper.appendChild(img);
        wrapper.appendChild(overlay);
        output.appendChild(wrapper);

        // When image loads, sync overlay + place words
        img.onload = () => {
            syncOverlaySize(img, overlay);
            placeWords(page.words, overlay);
            log("Rendered page");
        };
    });
}

// ------------------------------
// Sync overlay height to image
// ------------------------------
function syncOverlaySize(img, overlay) {
    overlay.style.width = img.clientWidth + "px";
    overlay.style.height = img.clientHeight + "px";
}

// ------------------------------
// Place words on overlay
// ------------------------------
function placeWords(words, overlay) {
    words.forEach((w) => {
        if (w.skip) return;

        const span = document.createElement("span");
        span.className = "word";

        if (w.definition) {
            span.classList.add("has-definition");
            span.title = `${w.term}: ${w.definition}`;
        }

        span.textContent = w.term || w.text;

        // Positioning
        span.style.left = w.x + "px";
        span.style.top = w.y + "px";
        span.style.width = w.width + "px";
        span.style.height = w.height + "px";

        overlay.appendChild(span);
    });
}

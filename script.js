const pdfInput = document.getElementById("pdf-input");
const processBtn = document.getElementById("process-btn");
const logEl = document.getElementById("log");
const pageViewer = document.getElementById("page-viewer");
const outputEl = document.getElementById("output");
const metaEl = document.getElementById("meta");

let pdfFile = null;

// ---- Logging helper ----
function log(message) {
  const timestamp = new Date().toLocaleTimeString();
  logEl.textContent += `[${timestamp}] ${message}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

// ---- UI helpers ----
function setProcessing(isProcessing) {
  processBtn.disabled = isProcessing || !pdfFile;
  pdfInput.disabled = isProcessing;
  processBtn.textContent = isProcessing ? "Processing…" : "Reconstruct layout";
}

// ---- File selection ----
pdfInput.addEventListener("change", (e) => {
  pdfFile = e.target.files[0] || null;
  logEl.textContent = ""; // reset log
  if (pdfFile) {
    log(`Selected PDF: ${pdfFile.name} (${Math.round(pdfFile.size / 1024)} KB)`);
    processBtn.disabled = false;
  } else {
    log("No file selected.");
    processBtn.disabled = true;
  }
});

// ---- Main processing ----
processBtn.addEventListener("click", async () => {
  if (!pdfFile) return;

  setProcessing(true);
  pageViewer.innerHTML = '<p class="placeholder">Processing PDF…</p>';
  outputEl.innerHTML = "";
  metaEl.innerHTML = "";
  log("Starting upload to backend /extract endpoint…");

  try {
    const formData = new FormData();
    formData.append("file", pdfFile);

    const response = await fetch("https://article-assist-backend.onrender.com/extract", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Server responded with status ${response.status}`);
    }

    const data = await response.json();
    log("Received response from backend.");

    renderMeta(data.meta);
    renderPages(data.pages);
    renderText(data.pages);

    log("Done. Layout reconstruction displayed.");
  } catch (err) {
    console.error(err);
    log(`Error: ${err.message}`);
    pageViewer.innerHTML =
      '<p class="placeholder error">An error occurred while processing the PDF.</p>';
    outputEl.innerHTML =
      '<p class="placeholder error">Unable to display reconstructed text.</p>';
  } finally {
    setProcessing(false);
  }
});

// ---- Rendering helpers ----
function renderMeta(meta = {}) {
  if (!meta || (!meta.title && !meta.authors)) {
    metaEl.innerHTML = "";
    return;
  }

  const parts = [];
  if (meta.title) {
    parts.push(`<div class="meta-title">${meta.title}</div>`);
  }
  if (Array.isArray(meta.authors) && meta.authors.length > 0) {
    parts.push(
      `<div class="meta-authors">${meta.authors.join(", ")}</div>`
    );
  }
  metaEl.innerHTML = parts.join("");
}

function renderPages(pages = []) {
  if (!Array.isArray(pages) || pages.length === 0) {
    pageViewer.innerHTML =
      '<p class="placeholder">No pages returned from backend.</p>';
    return;
  }

  pageViewer.innerHTML = "";
  pages.forEach((page) => {
    if (!page.image_url) return;

    const wrapper = document.createElement("div");
    wrapper.className = "page-wrapper-item";

    const label = document.createElement("div");
    label.className = "page-label";
    label.textContent = `Page ${page.page_number ?? "?"}`;

    const img = document.createElement("img");
    img.className = "page-image";
    img.src = page.image_url;
    img.alt = `Page ${page.page_number ?? ""}`;

    wrapper.appendChild(label);
    wrapper.appendChild(img);
    pageViewer.appendChild(wrapper);
  });
}

function renderText(pages = []) {
  if (!Array.isArray(pages) || pages.length === 0) {
    outputEl.innerHTML =
      '<p class="placeholder">No reconstructed text returned from backend.</p>';
    return;
  }

  outputEl.innerHTML = "";
  pages.forEach((page) => {
    const pageBlock = document.createElement("article");
    pageBlock.className = "page-text-block";

    const heading = document.createElement("h3");
    heading.className = "page-text-heading";
    heading.textContent = `Page ${page.page_number ?? "?"}`;

    const body = document.createElement("div");
    body.className = "page-text-body";

    const para = document.createElement("p");
    para.textContent = page.text || "";
    body.appendChild(para);

    pageBlock.appendChild(heading);
    pageBlock.appendChild(body);
    outputEl.appendChild(pageBlock);
  });
}

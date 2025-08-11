const $ = (sel) => document.querySelector(sel);
const gallery = $("#gallery");
const searchInput = $("#search");
const countTag = $("#count");
const dropzone = $("#dropzone");
const fileInput = $("#fileInput");
const browseBtn = $("#browseBtn");
const refreshBtn = $("#refreshBtn");
const modal = $("#modal");
const modalTitle = $("#modalTitle");
const modalImg = $("#modalImg");
const modalSize = $("#modalSize");
const modalClose = $("#modalClose");
const modalDownload = $("#modalDownload");

let allItems = [];   // entire list from server
let filtered = [];   // filtered by client-side search

async function fetchImages(q = "") {
  const url = new URL(`${API_BASE}/api/images`, location.origin);
  if (API_BASE === "") url.pathname = "/api/images"; // same origin when bundled
  if (q) url.searchParams.set("search", q);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Failed to load images");
  return res.json();
}

function render(items) {
  gallery.innerHTML = "";
  if (!items.length) {
    gallery.innerHTML = `<div class="empty" style="grid-column: 1/-1; color: var(--muted); text-align:center">No images yet.</div>`;
  } else {
    for (const it of items) {
      const card = document.createElement("article");
      card.className = "card";
      card.innerHTML = `
        <div class="thumb" data-id="${it.id}" title="Open preview">
          <img alt="${it.name}" src="${it.url}" loading="lazy" />
        </div>
        <div class="meta">
          <div class="name" title="${it.name}">${it.name}</div>
          <div class="row">
            <small class="muted">${it.width}×${it.height}</small>
            <a class="btn" href="${it.url}" download="${safeName(it.name)}.png">Download</a>
          </div>
        </div>
      `;
      gallery.appendChild(card);
    }
  }
  countTag.textContent = `${items.length} shown`;
}

function safeName(name) {
  return name.replace(/\.[^.]+$/, "").replace(/[^\w\-]+/g, "_");
}

async function refreshList() {
  const q = searchInput.value.trim();
  allItems = await fetchImages(q);
  filtered = allItems; // server already filtered by q
  render(filtered);
}

async function uploadFiles(files) {
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error("Upload failed");
  await refreshList();
}

function openModal(item) {
  modalTitle.textContent = item.name;
  modalImg.src = item.url;
  modalImg.alt = item.name;
  modalSize.textContent = `${item.width}×${item.height}`;
  modalDownload.href = item.url;
  modalDownload.download = `${safeName(item.name)}.png`;
  if (!modal.open) modal.showModal();
}

function attachEvents() {
  browseBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files?.length) uploadFiles(e.target.files);
    fileInput.value = "";
  });
  refreshBtn.addEventListener("click", refreshList);

  searchInput.addEventListener("input", async () => {
    // Ask API to filter by filename (handles large datasets cheaply)
    await refreshList();
  });

  // Drag & drop
  ["dragenter", "dragover"].forEach(ev =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach(ev =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) uploadFiles(files);
  });

  // Gallery click → modal
  gallery.addEventListener("click", (e) => {
    const thumb = e.target.closest(".thumb");
    if (!thumb) return;
    const id = thumb.getAttribute("data-id");
    const item = filtered.find((x) => x.id === id);
    if (item) openModal(item);
  });

  modalClose.addEventListener("click", () => modal.close());
}

attachEvents();
refreshList().catch((e) => console.error(e));

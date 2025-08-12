import { Blp, BLP_IMAGE_FORMAT } from "https://cdn.jsdelivr.net/npm/@wowserhq/format@0.28.0/+esm";

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

// API_BASE is defined in index.html; it's "" for same-origin.
const API = (path) => `${window.API_BASE || ""}${path}`;

let allItems = [];
let filtered = [];

function safeName(name) {
  return name.replace(/\.[^.]+$/, "").replace(/[^\w\-]+/g, "_");
}

async function fetchImages(q = "") {
  const url = new URL(API("/api/images"), window.location.origin);
  if ((window.API_BASE || "") === "") url.pathname = "/api/images"; // same origin
  if (q) url.searchParams.set("search", q);
  const res = await fetch(url.toString(), { credentials: "omit" });
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

async function refreshList() {
  const q = searchInput.value.trim();
  allItems = await fetchImages(q);
  filtered = allItems; // server filtered by q
  render(filtered);
}

async function decodeBLPtoPNG(file) {
  const ab = await file.arrayBuffer();
  const blp = new Blp().load(ab);
  const img = blp.getImage(0, BLP_IMAGE_FORMAT.IMAGE_ABGR8888);
  const canvas = document.createElement("canvas");
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext("2d");
  const imageData = new ImageData(
    new Uint8ClampedArray(img.data.buffer),
    img.width,
    img.height
  );
  ctx.putImageData(imageData, 0, 0);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      const newFile = new File([blob], file.name.replace(/\.blp$/i, ".png"), {
        type: "image/png",
      });
      resolve(newFile);
    }, "image/png");
  });
}

// static/app.js

async function decodeTGAtoPNG(file) {
  const ab = await file.arrayBuffer();
  const tga = new TGA(new Uint8Array(ab));
  const imageData = tga.getImageData();

  const canvas = document.createElement("canvas");
  canvas.width = imageData.width;
  canvas.height = imageData.height;
  const ctx = canvas.getContext("2d");
  ctx.putImageData(imageData, 0, 0);

  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      const newFile = new File([blob], file.name.replace(/\.tga$/i, ".png"), {
        type: "image/png",
      });
      resolve(newFile);
    }, "image/png");
  });
}

// static/app.js

async function uploadFiles(files) {
  if (!files || files.length === 0) return;

  const fd = new FormData();
  for (const f of files) {
    const lowerName = f.name.toLowerCase();
    if (lowerName.endsWith(".blp")) {
      const pngFile = await decodeBLPtoPNG(f);
      fd.append("files", pngFile, pngFile.name);
    } else if (lowerName.endsWith(".tga")) { // 👈 ADD THIS ELSE IF BLOCK
      const pngFile = await decodeTGAtoPNG(f);
      fd.append("files", pngFile, pngFile.name);
    } else {
      fd.append("files", f, f.name);
    }
  }

  const res = await fetch(API("/api/upload"), { method: "POST", body: fd });
  if (!res.ok) {
    alert("Upload failed.");
    return;
  }
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
    await refreshList();
  });

  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault(); dropzone.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault(); dropzone.classList.remove("drag");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) uploadFiles(files);
  });

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

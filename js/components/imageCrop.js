import { state } from "../catalog.js";
import { byId as $ } from "../utils.js";

export function createImageCropController() {
function updateCoachImagePreview() {
  const preview = $("coachImagePreview");
  preview.style.backgroundImage = `url("${$("coachImage").value.trim() || "assets/logo.jpg"}")`;
  preview.style.backgroundPosition = "center center";
  preview.style.backgroundSize = "cover";
}

function updateWideImagePreview(inputId, previewId) {
  const preview = $(previewId);
  if (!preview) return;
  const image = $(inputId).value.trim();
  preview.style.backgroundImage = image ? `url("${image}")` : "none";
  preview.style.backgroundPosition = "center center";
  preview.style.backgroundSize = "cover";
  const empty = preview.querySelector(".image-preview-empty");
  if (empty) empty.hidden = Boolean(image);
}

function handleCoachImageFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    alert("이미지 파일만 선택할 수 있습니다.");
    event.target.value = "";
    return;
  }
  if (file.size > 1024 * 1024) {
    alert("이미지는 1MB 이하로 올려주세요. 큰 이미지는 저장 공간을 빠르게 채울 수 있습니다.");
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.cropSourceImage = String(reader.result || "");
    $("coachImage").value = state.cropSourceImage;
    updateCoachImagePreview();
    openCropModal({
      inputId: "coachImage",
      previewId: "coachImagePreview",
      width: 520,
      height: 520,
      label: "일반 목록 이미지",
    });
  });
  reader.readAsDataURL(file);
}

function handleCoachSelfProfileImageFile(event, inputId = "coachSelfProfileImage", previewId = "coachSelfProfileImagePreview", label = "프로필 이미지") {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    alert("이미지 파일만 선택할 수 있습니다.");
    event.target.value = "";
    return;
  }
  if (file.size > 1024 * 1024) {
    alert("이미지는 1MB 이하로 올려주세요.");
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.cropSourceImage = String(reader.result || "");
    $(inputId).value = state.cropSourceImage;
    updateWideImagePreview(inputId, previewId);
    openCropModal({
      inputId,
      previewId,
      width: 520,
      height: 520,
      label,
    });
  });
  reader.readAsDataURL(file);
}

function handleWideCoachImageFile(event, inputId, previewId, label) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    alert("이미지 파일만 선택할 수 있습니다.");
    event.target.value = "";
    return;
  }
  if (file.size > 3 * 1024 * 1024) {
    alert(`${label}는 3MB 이하로 올려주세요.`);
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.cropSourceImage = String(reader.result || "");
    $(inputId).value = state.cropSourceImage;
    updateWideImagePreview(inputId, previewId);
    openCropModal({ inputId, previewId, width: 1200, height: 675, label });
  });
  reader.readAsDataURL(file);
}

function openCropModal(target = null) {
  state.cropTarget = target || {
    inputId: "coachImage",
    previewId: "coachImagePreview",
    width: 520,
    height: 520,
    label: "일반 목록 이미지",
  };
  const image = state.cropSourceImage || $(state.cropTarget.inputId).value.trim();
  if (!image) return;
  $("cropImage").src = image;
  $("cropTitle").textContent = `${state.cropTarget.label} 범위 지정`;
  $("cropModal").hidden = false;
  $("cropX").value = 50;
  $("cropY").value = 50;
  $("cropSize").value = 60;
  setTimeout(updateCropBox, 0);
}

function closeCropModal() {
  $("cropModal").hidden = true;
}

function getCropRect() {
  const image = $("cropImage");
  const stage = image.getBoundingClientRect();
  const target = state.cropTarget || { width: 520, height: 520 };
  const ratio = target.width / target.height;
  const scale = Number($("cropSize").value) / 100;
  let maxWidth = stage.width;
  let maxHeight = maxWidth / ratio;
  if (maxHeight > stage.height) {
    maxHeight = stage.height;
    maxWidth = maxHeight * ratio;
  }
  const width = maxWidth * scale;
  const height = maxHeight * scale;
  const maxX = Math.max(0, stage.width - width);
  const maxY = Math.max(0, stage.height - height);
  const left = stage.left + maxX * (Number($("cropX").value) / 100);
  const top = stage.top + maxY * (Number($("cropY").value) / 100);
  return { left, top, width, height, imageRect: stage };
}

function updateCropBox() {
  const rect = getCropRect();
  const parentRect = document.querySelector(".crop-stage").getBoundingClientRect();
  const box = $("cropBox");
  box.style.width = `${rect.width}px`;
  box.style.height = `${rect.height}px`;
  box.style.left = `${rect.left - parentRect.left}px`;
  box.style.top = `${rect.top - parentRect.top}px`;
}

function setCropCenterFromPointer(event) {
  const rect = getCropRect();
  const imageRect = rect.imageRect;
  const maxX = Math.max(1, imageRect.width - rect.width);
  const maxY = Math.max(1, imageRect.height - rect.height);
  const left = Math.max(0, Math.min(maxX, event.clientX - imageRect.left - rect.width / 2));
  const top = Math.max(0, Math.min(maxY, event.clientY - imageRect.top - rect.height / 2));
  $("cropX").value = Math.round((left / maxX) * 100);
  $("cropY").value = Math.round((top / maxY) * 100);
  updateCropBox();
}

function moveCropToPointer(event) {
  if (event.target === $("cropImage")) {
    setCropCenterFromPointer(event);
  }
}

function startCropDrag(event) {
  event.preventDefault();
  event.stopPropagation();
  $("cropBox").setPointerCapture(event.pointerId);
  const onMove = (moveEvent) => setCropCenterFromPointer(moveEvent);
  const onEnd = () => {
    $("cropBox").removeEventListener("pointermove", onMove);
    $("cropBox").removeEventListener("pointerup", onEnd);
    $("cropBox").removeEventListener("pointercancel", onEnd);
  };
  $("cropBox").addEventListener("pointermove", onMove);
  $("cropBox").addEventListener("pointerup", onEnd);
  $("cropBox").addEventListener("pointercancel", onEnd);
}

function applyImageCrop() {
  const image = $("cropImage");
  if (!image.complete || !image.naturalWidth) return;
  const rect = getCropRect();
  const scaleX = image.naturalWidth / rect.imageRect.width;
  const scaleY = image.naturalHeight / rect.imageRect.height;
  const sourceX = Math.max(0, (rect.left - rect.imageRect.left) * scaleX);
  const sourceY = Math.max(0, (rect.top - rect.imageRect.top) * scaleY);
  const sourceWidth = rect.width * scaleX;
  const sourceHeight = rect.height * scaleY;
  const target = state.cropTarget || {
    inputId: "coachImage",
    previewId: "coachImagePreview",
    width: 520,
    height: 520,
  };
  const canvas = document.createElement("canvas");
  canvas.width = target.width;
  canvas.height = target.height;
  const context = canvas.getContext("2d");
  context.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
  $(target.inputId).value = canvas.toDataURL("image/jpeg", 0.78);
  if (target.inputId === "coachImage") {
    $("coachImagePosition").value = "center center";
    updateCoachImagePreview();
  } else {
    updateWideImagePreview(target.inputId, target.previewId);
  }
  state.cropSourceImage = "";
  state.cropTarget = null;
  closeCropModal();
}


  return {
    updateCoachImagePreview,
    updateWideImagePreview,
    handleCoachImageFile,
    handleCoachSelfProfileImageFile,
    handleWideCoachImageFile,
    openCropModal,
    closeCropModal,
    getCropRect,
    updateCropBox,
    setCropCenterFromPointer,
    moveCropToPointer,
    startCropDrag,
    applyImageCrop,
  };
}


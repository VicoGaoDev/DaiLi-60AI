import QRCode from "qrcode";

export const BRANDED_QR_SIZE = 192;
export const BRANDED_QR_ICON_URL = "/香蕉.svg";

function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Failed to load image: ${src}`));
    image.src = src;
  });
}

function fillRoundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const maxRadius = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + maxRadius, y);
  context.arcTo(x + width, y, x + width, y + height, maxRadius);
  context.arcTo(x + width, y + height, x, y + height, maxRadius);
  context.arcTo(x, y + height, x, y, maxRadius);
  context.arcTo(x, y, x + width, y, maxRadius);
  context.closePath();
  context.fill();
}

async function drawQrBrand(context: CanvasRenderingContext2D, size = BRANDED_QR_SIZE) {
  const badgeSize = 54;
  const badgeX = (size - badgeSize) / 2;
  const badgeY = (size - badgeSize) / 2;

  context.save();
  context.fillStyle = "#ffffff";
  context.shadowColor = "rgba(15, 23, 42, 0.12)";
  context.shadowBlur = 12;
  context.shadowOffsetY = 3;
  fillRoundedRect(context, badgeX, badgeY, badgeSize, badgeSize, 16);
  context.restore();

  try {
    const icon = await loadImage(BRANDED_QR_ICON_URL);
    const iconSize = 34;
    const iconX = (size - iconSize) / 2;
    const iconY = (size - iconSize) / 2;
    context.drawImage(icon, iconX, iconY, iconSize, iconSize);
  } catch {
    context.save();
    context.fillStyle = "#7c8f12";
    context.font = "700 15px Inter, PingFang SC, Microsoft YaHei, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText("80AI", size / 2, size / 2 + 1);
    context.restore();
  }
}

export async function createBrandedQrDataUrl(link: string, size = BRANDED_QR_SIZE): Promise<string> {
  if (!link) return "";
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  await QRCode.toCanvas(canvas, link, {
    width: size,
    margin: 1,
    errorCorrectionLevel: "H",
  });
  const context = canvas.getContext("2d");
  if (!context) throw new Error("二维码画布初始化失败");
  await drawQrBrand(context, size);
  return canvas.toDataURL("image/png");
}

export async function copyImageDataUrlToClipboard(dataUrl: string): Promise<void> {
  if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) {
    throw new Error("clipboard-image-unsupported");
  }
  const response = await fetch(dataUrl);
  const blob = await response.blob();
  await navigator.clipboard.write([
    new ClipboardItem({
      [blob.type || "image/png"]: blob,
    }),
  ]);
}

export function downloadDataUrl(dataUrl: string, filename: string) {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

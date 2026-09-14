import client from "./client";
import type { UploadCredential, UploadPurpose } from "@/types";

export const MAX_IMAGE_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;
export const MAX_IMAGE_UPLOAD_SIZE_TEXT = "20MB";
const JPEG_TO_WEBP_QUALITY = 0.9;
const ALLOWED_IMAGE_UPLOAD_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);
const IMAGE_EXTENSION_TYPES: Array<[RegExp, string]> = [
  [/\.(jpe?g)$/i, "image/jpeg"],
  [/\.png$/i, "image/png"],
  [/\.webp$/i, "image/webp"],
  [/\.gif$/i, "image/gif"],
];

export function inferImageContentType(file: File) {
  if (file.type && ALLOWED_IMAGE_UPLOAD_TYPES.has(file.type)) return file.type;
  const name = file.name.toLowerCase();
  for (const [pattern, contentType] of IMAGE_EXTENSION_TYPES) {
    if (pattern.test(name)) return contentType;
  }
  return file.type || "application/octet-stream";
}

export function isSupportedImageUploadFile(file: File) {
  return ALLOWED_IMAGE_UPLOAD_TYPES.has(inferImageContentType(file));
}

export const IMAGE_FILE_ACCEPT_GALLERY = "image/*";
export const IMAGE_FILE_ACCEPT_FILES = "*/*";
export const IMAGE_FILE_ACCEPT_DESKTOP = IMAGE_FILE_ACCEPT_GALLERY;

export function isMobileUploadDevice() {
  if (typeof navigator === "undefined") return false;
  const userAgent = navigator.userAgent || "";
  if (/Android|iPhone|iPod|Mobile/i.test(userAgent)) return true;
  if (/iPad/i.test(userAgent)) return true;
  return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
}

export function getImageFileAccept(source: "camera" | "gallery" | "files" = "gallery") {
  if (!isMobileUploadDevice()) return IMAGE_FILE_ACCEPT_DESKTOP;
  return source === "files" ? IMAGE_FILE_ACCEPT_FILES : IMAGE_FILE_ACCEPT_GALLERY;
}

export function isImageUploadTooLarge(file: File) {
  return file.size > MAX_IMAGE_UPLOAD_SIZE_BYTES;
}

function isJpegImage(file: File) {
  return inferImageContentType(file) === "image/jpeg";
}

function buildWebpFileName(fileName: string) {
  return fileName.replace(/\.[^.]+$/, "") + ".webp";
}

function loadImageFromObjectUrl(objectUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("JPEG 图片加载失败，无法转换为 WebP"));
    image.src = objectUrl;
  });
}

async function convertJpegToWebp(file: File): Promise<File> {
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await loadImageFromObjectUrl(objectUrl);
    const width = image.naturalWidth || image.width;
    const height = image.naturalHeight || image.height;
    if (!width || !height) {
      throw new Error("JPEG 图片尺寸无效，无法转换为 WebP");
    }

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("浏览器不支持 Canvas 2D，无法转换为 WebP");
    }
    context.drawImage(image, 0, 0, width, height);

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/webp", JPEG_TO_WEBP_QUALITY);
    });
    if (!blob) {
      throw new Error("浏览器不支持导出 WebP，无法转换图片");
    }

    return new File([blob], buildWebpFileName(file.name), {
      type: "image/webp",
      lastModified: file.lastModified || Date.now(),
    });
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

async function prepareUploadFile(file: File): Promise<File> {
  if (!isJpegImage(file)) return file;
  try {
    return await convertJpegToWebp(file);
  } catch (error) {
    console.warn("JPEG 转 WebP 失败，回退原图上传", error);
    return file;
  }
}

function getUploadCredential(file: File, purpose: UploadPurpose): Promise<UploadCredential> {
  return client.post("/upload/credential", {
    file_name: file.name,
    file_size: file.size,
    content_type: inferImageContentType(file),
    purpose,
  });
}

async function createCosClient(credential: UploadCredential) {
  const cosModule = await import("cos-js-sdk-v5");
  const COS = cosModule.default || cosModule;
  return new COS({
    Domain: credential.upload_domain || undefined,
    Protocol: "https:",
    getAuthorization(_, callback) {
      callback({
        TmpSecretId: credential.tmp_secret_id,
        TmpSecretKey: credential.tmp_secret_key,
        SecurityToken: credential.session_token,
        StartTime: credential.start_time || Math.floor(Date.now() / 1000),
        ExpiredTime: credential.expired_time,
      });
    },
  });
}

export function uploadReferenceImage(
  file: File,
  purpose: UploadPurpose = "ref",
  onProgress?: (percent: number) => void,
): Promise<{ url: string; key: string }> {
  return new Promise(async (resolve, reject) => {
    try {
      const uploadFile = await prepareUploadFile(file);
      const credential = await getUploadCredential(uploadFile, purpose);
      const cos = await createCosClient(credential);

      cos.putObject(
        {
          Bucket: credential.bucket,
          Region: credential.region,
          Key: credential.key,
          Body: uploadFile,
          onProgress(progressData) {
            onProgress?.((progressData.percent || 0) * 100);
          },
        },
        (err) => {
          if (err) {
            reject(err);
            return;
          }
          resolve({ url: credential.url, key: credential.key });
        },
      );
    } catch (error) {
      reject(error);
    }
  });
}

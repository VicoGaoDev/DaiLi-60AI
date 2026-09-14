import client from "./client";
import type {
  UploadCredential,
  UserAsset,
  UserAssetCategory,
  UserAssetCategoryListResponse,
  UserAssetImportResponse,
  UserAssetListResponse,
  UserAssetQuota,
  UserAssetUploadSessionResponse,
} from "@/types";

const MAX_IMAGE_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;
const JPEG_TO_WEBP_QUALITY = 0.9;

function inferImageContentType(file: File) {
  if (file.type) return file.type;
  const name = file.name.toLowerCase();
  if (/\.(jpe?g)$/.test(name)) return "image/jpeg";
  if (/\.png$/.test(name)) return "image/png";
  if (/\.webp$/.test(name)) return "image/webp";
  if (/\.gif$/.test(name)) return "image/gif";
  return "application/octet-stream";
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

async function uploadWithCredential(
  file: File,
  credential: UploadCredential,
  onProgress?: (percent: number) => void,
): Promise<void> {
  const cos = await createCosClient(credential);
  return new Promise((resolve, reject) => {
    cos.putObject(
      {
        Bucket: credential.bucket,
        Region: credential.region,
        Key: credential.key,
        Body: file,
        onProgress(progressData) {
          onProgress?.((progressData.percent || 0) * 100);
        },
      },
      (err) => {
        if (err) {
          reject(err);
          return;
        }
        resolve();
      },
    );
  });
}

function readImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      resolve({
        width: image.naturalWidth || image.width || 0,
        height: image.naturalHeight || image.height || 0,
      });
      URL.revokeObjectURL(objectUrl);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("读取图片尺寸失败"));
    };
    image.src = objectUrl;
  });
}

export function listUserAssetCategories(): Promise<UserAssetCategoryListResponse> {
  return client.get("/user-assets/categories");
}

export function createUserAssetCategory(name: string): Promise<UserAssetCategory> {
  return client.post("/user-assets/categories", { name });
}

export function updateUserAssetCategory(categoryId: number, name: string): Promise<UserAssetCategory> {
  return client.patch(`/user-assets/categories/${categoryId}`, { name });
}

export function deleteUserAssetCategory(categoryId: number): Promise<void> {
  return client.delete(`/user-assets/categories/${categoryId}`);
}

export function listUserAssets(params?: {
  categoryId?: number | null;
  keyword?: string;
  limit?: number;
}): Promise<UserAssetListResponse> {
  const query: Record<string, any> = {};
  if (typeof params?.categoryId === "number") query.category_id = params.categoryId;
  if (params?.keyword?.trim()) query.keyword = params.keyword.trim();
  if (params?.limit) query.limit = params.limit;
  return client.get("/user-assets", { params: query });
}

export function getUserAssetStats(): Promise<UserAssetQuota> {
  return client.get("/user-assets/stats");
}

export function createUserAssetUploadSession(payload: {
  fileName: string;
  fileSize: number;
  contentType: string;
  categoryId?: number | null;
}): Promise<UserAssetUploadSessionResponse> {
  return client.post("/user-assets/upload-session", {
    file_name: payload.fileName,
    file_size: payload.fileSize,
    content_type: payload.contentType,
    category_id: payload.categoryId ?? null,
  });
}

export function importUserAssetFromUrl(payload: {
  imageUrl: string;
  fileName: string;
  categoryId?: number | null;
  width?: number | null;
  height?: number | null;
}): Promise<UserAssetImportResponse> {
  return client.post("/user-assets/import", {
    image_url: payload.imageUrl,
    file_name: payload.fileName,
    category_id: payload.categoryId ?? null,
    width: payload.width ?? null,
    height: payload.height ?? null,
  });
}

export function completeUserAssetUpload(assetId: number, payload?: {
  width?: number | null;
  height?: number | null;
}): Promise<UserAsset> {
  return client.post(`/user-assets/${assetId}/complete`, {
    width: payload?.width ?? null,
    height: payload?.height ?? null,
  });
}

export function updateUserAsset(assetId: number, payload: {
  categoryId?: number | null;
  fileName?: string;
}): Promise<UserAsset> {
  const body: Record<string, any> = {};
  if ("categoryId" in payload) body.category_id = payload.categoryId ?? null;
  if (typeof payload.fileName !== "undefined") body.file_name = payload.fileName;
  return client.patch(`/user-assets/${assetId}`, body);
}

export function deleteUserAsset(assetId: number): Promise<{ quota: UserAssetQuota }> {
  return client.delete(`/user-assets/${assetId}`);
}

export async function uploadUserAssetFile(
  file: File,
  options?: {
    categoryId?: number | null;
    onProgress?: (percent: number) => void;
  },
): Promise<{ asset: UserAsset; quota: UserAssetQuota }> {
  if (file.size > MAX_IMAGE_UPLOAD_SIZE_BYTES) {
    throw new Error("图片大小不能超过 20MB");
  }

  const uploadFile = await prepareUploadFile(file);
  const session = await createUserAssetUploadSession({
    fileName: uploadFile.name,
    fileSize: uploadFile.size,
    contentType: inferImageContentType(uploadFile),
    categoryId: options?.categoryId ?? null,
  });

  try {
    await uploadWithCredential(uploadFile, session.credential, options?.onProgress);
    const dimensions = await readImageDimensions(uploadFile).catch(() => ({ width: 0, height: 0 }));
    const asset = await completeUserAssetUpload(session.asset.id, {
      width: dimensions.width || null,
      height: dimensions.height || null,
    });
    return {
      asset,
      quota: {
        ...session.quota,
        used: session.quota.used,
        remaining: session.quota.remaining,
      },
    };
  } catch (error) {
    try {
      await deleteUserAsset(session.asset.id);
    } catch {
      // Ignore cleanup errors and surface the original upload failure.
    }
    throw error;
  }
}

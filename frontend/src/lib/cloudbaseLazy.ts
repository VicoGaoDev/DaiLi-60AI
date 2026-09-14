type CloudbaseAuth = typeof import("./cloudbase");

let cloudbaseAuth: Promise<CloudbaseAuth> | null = null;

export function loadCloudbaseAuth() {
  if (!cloudbaseAuth) {
    cloudbaseAuth = import("./cloudbase").catch((error) => {
      cloudbaseAuth = null;
      throw error;
    });
  }
  return cloudbaseAuth;
}

export function preloadCloudbaseAuth() {
  void loadCloudbaseAuth().catch((error) => {
    console.warn("Failed to preload CloudBase auth", error);
  });
}

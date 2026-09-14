import { nextTick, ref } from "vue";
import {
  IMAGE_FILE_ACCEPT_DESKTOP,
  IMAGE_FILE_ACCEPT_FILES,
  IMAGE_FILE_ACCEPT_GALLERY,
  isMobileUploadDevice,
} from "@/api/upload";

type PickerCallbacks = {
  onOpen?: () => void;
  onCancel?: () => void;
};

export function useImageSourcePicker() {
  const accept = ref(IMAGE_FILE_ACCEPT_DESKTOP);
  const sheetOpen = ref(false);
  let pendingInput: HTMLInputElement | null = null;
  let pendingCallbacks: PickerCallbacks | null = null;

  function applyCapture(input: HTMLInputElement, capture?: string) {
    if (capture) {
      input.setAttribute("capture", capture);
      return;
    }
    input.removeAttribute("capture");
  }

  function requestPick(input: HTMLInputElement | null, callbacks?: PickerCallbacks) {
    if (!input) return;

    if (!isMobileUploadDevice()) {
      accept.value = IMAGE_FILE_ACCEPT_DESKTOP;
      applyCapture(input);
      callbacks?.onOpen?.();
      input.click();
      return;
    }

    pendingInput = input;
    pendingCallbacks = callbacks || null;
    sheetOpen.value = true;
  }

  async function finishPick(nextAccept: string, capture?: string) {
    const input = pendingInput;
    const callbacks = pendingCallbacks;
    pendingInput = null;
    pendingCallbacks = null;
    sheetOpen.value = false;
    if (!input) return;

    accept.value = nextAccept;
    applyCapture(input, capture);
    callbacks?.onOpen?.();
    await nextTick();
    input.click();
  }

  function pickFromCamera() {
    void finishPick(IMAGE_FILE_ACCEPT_GALLERY, "environment");
  }

  function pickFromGallery() {
    void finishPick(IMAGE_FILE_ACCEPT_GALLERY);
  }

  function pickFromFiles() {
    void finishPick(IMAGE_FILE_ACCEPT_FILES);
  }

  function cancelSheet() {
    const callbacks = pendingCallbacks;
    pendingInput = null;
    pendingCallbacks = null;
    sheetOpen.value = false;
    callbacks?.onCancel?.();
  }

  return {
    accept,
    sheetOpen,
    requestPick,
    pickFromCamera,
    pickFromGallery,
    pickFromFiles,
    cancelSheet,
  };
}

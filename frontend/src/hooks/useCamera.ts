import { useCallback, useEffect, useRef, useState } from "react";

export function useCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // Monotonic counter used to invalidate in-flight getUserMedia() requests so a
  // superseded request never leaks a live stream or overwrites state.
  const generationRef = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(false);

  const stop = useCallback(() => {
    // Invalidate any pending start(): when it resolves, it will release its
    // stream instead of keeping the camera running.
    generationRef.current += 1;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setActive(false);
  }, []);

  const start = useCallback(async () => {
    // Always release any previous stream before requesting a new one.
    stop();
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Camera is not supported in this browser.");
      return;
    }

    const gen = generationRef.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false,
      });

      // If stop() (or a newer start()) ran while we were waiting, release this
      // stream immediately so the camera does not stay on.
      if (gen !== generationRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        try {
          await videoRef.current.play();
        } catch {
          // play() can be interrupted if the element is detached; not fatal.
        }
      }
      setActive(true);
    } catch (e) {
      if (gen !== generationRef.current) {
        return; // superseded request; ignore
      }
      const msg = e instanceof Error ? e.message : String(e);
      if (/denied|notallowed|permission/i.test(msg)) {
        setError("Camera permission was denied. Please allow camera access and retry.");
      } else if (/aborted/i.test(msg)) {
        setError("Camera access was interrupted. Please retry.");
      } else if (/notfound|nodevice|no camera/i.test(msg)) {
        setError("No camera was found on this device.");
      } else {
        setError(`Unable to start camera: ${msg}`);
      }
      stop(); // ensure nothing is left running on error
    }
  }, [stop]);

  const capture = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      const video = videoRef.current;
      if (!video || !video.videoWidth) {
        reject(new Error("No video frame available."));
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas is not available."));
        return;
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Capture failed."))), "image/png");
    });
  }, []);

  // Stop the camera when the consuming component unmounts.
  useEffect(() => () => stop(), [stop]);

  return { videoRef, error, active, start, stop, capture };
}


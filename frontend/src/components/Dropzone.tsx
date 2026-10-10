import { useRef, useState } from "react";

interface DropzoneProps {
  onFile: (file: File) => void;
  accept?: string;
}

export function Dropzone({ onFile, accept = "image/jpeg,image/png,image/webp" }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [drag, setDrag] = useState(false);

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-8 text-center transition ${
        drag ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-white"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
    >
      <p className="text-slate-600">Drag &amp; drop a Voter ID image here, or</p>
      <button
        type="button"
        className="mt-3 rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        onClick={() => inputRef.current?.click()}
      >
        Choose file
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <p className="mt-2 text-xs text-slate-400">JPG, PNG or WebP (max 15 MB)</p>
    </div>
  );
}

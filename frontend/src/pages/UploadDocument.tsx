import { useState } from "react";
import { Dropzone } from "../components/Dropzone";

interface UploadDocumentProps {
  onUpload: (front: File | null, back: File | null) => void;
  error: string | null;
}

function SideCard({
  title,
  required,
  file,
  preview,
  onChoose,
  onRemove,
}: {
  title: string;
  required?: boolean;
  file: File | null;
  preview: string | null;
  onChoose: (f: File) => void;
  onRemove: () => void;
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h3 className="font-medium text-slate-800">
        {title} {required ? <span className="text-red-500">*</span> : <span className="text-xs text-slate-400">(optional)</span>}
      </h3>
      <div className="mt-3">
        {preview ? (
          <div>
            <img src={preview} alt={`${title} preview`} className="max-h-56 rounded border" />
            <p className="mt-1 truncate text-xs text-slate-500">{file?.name}</p>
            <button
              type="button"
              onClick={onRemove}
              className="mt-2 rounded-md bg-slate-100 px-3 py-1 text-sm hover:bg-slate-200"
            >
              Remove
            </button>
          </div>
        ) : (
          <Dropzone onFile={onChoose} />
        )}
      </div>
    </div>
  );
}

export function UploadDocument({ onUpload, error }: UploadDocumentProps) {
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);
  const [frontUrl, setFrontUrl] = useState<string | null>(null);
  const [backUrl, setBackUrl] = useState<string | null>(null);

  const chooseFront = (f: File) => {
    if (frontUrl) URL.revokeObjectURL(frontUrl);
    setFront(f);
    setFrontUrl(URL.createObjectURL(f));
  };
  const chooseBack = (f: File) => {
    if (backUrl) URL.revokeObjectURL(backUrl);
    setBack(f);
    setBackUrl(URL.createObjectURL(f));
  };
  const removeFront = () => {
    if (frontUrl) URL.revokeObjectURL(frontUrl);
    setFront(null);
    setFrontUrl(null);
  };
  const removeBack = () => {
    if (backUrl) URL.revokeObjectURL(backUrl);
    setBack(null);
    setBackUrl(null);
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl bg-white p-8 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900">Upload Voter ID</h2>
        <p className="mt-1 text-sm text-slate-600">
          Upload the <strong>front</strong> of the card (required) and the <strong>back</strong> if
          available. Both images are kept; the front is used for analysis.
        </p>

        <div className="mt-4 grid grid-cols-1 gap-4">
          <SideCard
            title="Front"
            required
            file={front}
            preview={frontUrl}
            onChoose={chooseFront}
            onRemove={removeFront}
          />
          <SideCard
            title="Back"
            file={back}
            preview={backUrl}
            onChoose={chooseBack}
            onRemove={removeBack}
          />
        </div>

        {error && <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={() => onUpload(front, back)}
            disabled={!front}
            className="rounded-md bg-blue-600 px-5 py-2 font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Continue to Analysis
          </button>
        </div>
      </div>
    </div>
  );
}


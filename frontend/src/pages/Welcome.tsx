export function Welcome({ onStart }: { onStart: () => void }) {
  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Voter ID Verification Prototype</h1>
        <p className="mt-3 text-slate-600">
          This tool verifies an Indian Voter ID (EPIC) document and compares a live camera
          photograph against the portrait on the card.
        </p>

        <ol className="mt-5 list-decimal space-y-2 pl-5 text-slate-700">
          <li>Upload a clear photo of the front of your Voter ID card.</li>
          <li>We extract and cross-verify the printed information locally.</li>
          <li>You capture a live photo which is compared with the card portrait.</li>
          <li>A report shows whether each check passed, failed, or needs review.</li>
        </ol>

        <div className="mt-6 rounded-md bg-amber-50 p-4 text-sm text-amber-800">
          <p className="font-semibold">Privacy notice</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>Images are processed locally on your machine and deleted when the session ends.</li>
            <li>By continuing you consent to local processing of the uploaded document and a live capture.</li>
            <li>This is a demonstration, not an official Election Commission of India verification.</li>
          </ul>
        </div>

        <button
          type="button"
          onClick={onStart}
          className="mt-6 w-full rounded-md bg-blue-600 py-3 text-lg font-semibold text-white hover:bg-blue-700"
        >
          Start Verification
        </button>
      </div>
    </div>
  );
}

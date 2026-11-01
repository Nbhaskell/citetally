import { useRef, useState, type DragEvent } from "react";

import Icon from "./Icon";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

/** Drop files, choose files, or take a photo. What happens next is the page's job. */
export default function UploadArea({
  onFiles,
  busy,
}: {
  onFiles: (files: File[]) => void;
  busy: boolean;
}) {
  const choose = useRef<HTMLInputElement>(null);
  const photo = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const hasCamera = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices);

  function take(list: FileList | null) {
    const files = list ? Array.from(list) : [];
    if (files.length > 0) onFiles(files);
  }
  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    take(event.dataTransfer.files);
  }

  return (
    <section
      className={`upload${dragging ? " upload-over" : ""}`}
      aria-labelledby="upload-title"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <div className="upload-copy">
        <h2 id="upload-title">Add invoices and receipts</h2>
        <p>Drop PDF, PNG or JPEG files here. Lay the page flat, fill the frame, good light, no glare.</p>
      </div>
      <div className="upload-buttons">
        <button type="button" className="button" disabled={busy} onClick={() => choose.current?.click()}>
          <Icon name="upload" />
          Choose files
        </button>
        {hasCamera && (
          <button type="button" className="button" disabled={busy} onClick={() => photo.current?.click()}>
            <Icon name="camera" />
            Take a photo
          </button>
        )}
      </div>
      <input
        ref={choose}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        aria-label="Choose files"
        data-testid="file-input"
        onChange={(event) => {
          take(event.target.files);
          event.target.value = "";
        }}
      />
      <input
        ref={photo}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        aria-label="Take a photo"
        onChange={(event) => {
          take(event.target.files);
          event.target.value = "";
        }}
      />
    </section>
  );
}

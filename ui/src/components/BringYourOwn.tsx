/**
 * Secondary "Bring your own" affordance — wraps FileUpload with a section
 * heading per the design audit's two-pane layout. Visual hierarchy: the
 * SampleReplayList above is the hero path; this is the alternate route for
 * users who already have a session JSON.
 */

import { FileUpload } from "./FileUpload";

interface Props {
  onFile: (file: File) => void;
  isUploading: boolean;
  error?: string | null;
}

export function BringYourOwn({ onFile, isUploading, error }: Props) {
  return (
    <section aria-labelledby="bring-your-own-heading">
      <h3
        id="bring-your-own-heading"
        className="text-[11px] uppercase tracking-wider text-muted font-mono mb-2"
      >
        Bring your own
      </h3>
      <FileUpload onFile={onFile} isUploading={isUploading} error={error} />
    </section>
  );
}

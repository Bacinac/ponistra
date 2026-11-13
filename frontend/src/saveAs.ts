import { useMutation } from '@tanstack/react-query';
import { saveJob } from './jobs';

export type Saved = 'docx' | 'docm' | 'pdf' | 'xlsx' | 'xlsm' | 'csv' | 'pptx' | 'pptm' | 'ponx';

interface Asked {
  format: Saved;
  title: string;
  /** PONISTRA's own file only: the document's versions go with it. */
  versions?: boolean;
}

/** The document saved as a file of the format, which the server makes. */
export function useSaveAs(nodeId: string) {
  return useMutation({
    mutationFn: ({ format, title, versions = false }: Asked) =>
      saveJob(format, { document: nodeId, versions }, `${title}.${format}`),
  });
}

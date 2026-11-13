import {
  getDocument,
  GlobalWorkerOptions,
  InvalidPDFException,
  PasswordException,
  PermissionFlag,
  ResponseException,
  version,
  type PDFDocumentProxy,
} from 'pdfjs-dist';
import worker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { ApiError } from '../api';
import { errorMessage } from '../tree';

GlobalWorkerOptions.workerSrc = worker;

/** Served by `pdfjsData` in vite.config.ts. */
export const DATA = `/assets/pdfjs-${version}/`;

/** A file opened by byte ranges, only the parts of the pages drawn fetched. */
export function load(url: string) {
  return getDocument({
    url,
    disableStream: true,
    disableAutoFetch: true,
    enableXfa: false,
    cMapUrl: `${DATA}cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${DATA}standard_fonts/`,
    wasmUrl: `${DATA}wasm/`,
    iccUrl: `${DATA}iccs/`,
  });
}

export function failure(error: Error, url: string, t: Parameters<typeof errorMessage>[1]): string {
  if (error instanceof InvalidPDFException) return t('error.unreadable');
  if (error instanceof ResponseException) {
    return errorMessage(new ApiError(url, error.status, undefined), t);
  }
  return errorMessage(error, t);
}

/** Why a file's pages cannot be taken into another: a password, which the server is never
 * given, or the file's own permissions. */
export type Sealed = 'password' | 'assembly';

export async function forbidsAssembly(pdf: PDFDocumentProxy): Promise<boolean> {
  const allowed = await pdf.getPermissions();
  return allowed !== null && !allowed.has(PermissionFlag.ASSEMBLE);
}

/** Why a file cannot be blacked out: a password, which the server is never given, or the file's
 * own permissions. */
export type Unchangeable = 'password' | 'modify';

export async function forbidsChange(pdf: PDFDocumentProxy): Promise<boolean> {
  const allowed = await pdf.getPermissions();
  return allowed !== null && !allowed.has(PermissionFlag.MODIFY_CONTENTS);
}

/** The file opened for its pages to be taken into another, or why they cannot be. */
export async function take(url: string): Promise<PDFDocumentProxy | Sealed> {
  const task = load(url);
  try {
    const pdf = await task.promise;
    if (!(await forbidsAssembly(pdf))) return pdf;
    void task.destroy();
    return 'assembly';
  } catch (error) {
    void task.destroy();
    if (error instanceof PasswordException) return 'password';
    throw error;
  }
}

export async function sealedOf(url: string): Promise<Sealed | null> {
  const taken = await take(url);
  if (typeof taken === 'string') return taken;
  void taken.loadingTask.destroy();
  return null;
}

import { type NextRequest, NextResponse } from "next/server";

import { aiStatus } from "@/lib/personal/agents/llm";
import { extractPdfWithAi } from "@/lib/personal/documents/ai-extract";
import { extractFromText, kindFor, MAX_UPLOAD_BYTES } from "@/lib/personal/documents/extract";
import { jsonError, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { audit, consumeRateLimit, newId, type DocumentRecord } from "@/lib/personal/store";

export const dynamic = "force-dynamic";
export const maxDuration = 90;

const MAX_DOCUMENTS = 20;

/** Upload a document (.txt, .csv or .pdf, ≤ 2 MB). Extraction results await user review. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  if (Number(request.headers.get("content-length") ?? "0") > MAX_UPLOAD_BYTES + 64_000) return jsonError(413, "File too large (max 2 MB)");
  const session = await getSession();
  if (!consumeRateLimit(session)) return jsonError(429, "Too many requests. Wait a minute and try again.");
  if (session.documents.length >= MAX_DOCUMENTS) return jsonError(409, "Document limit reached; remove some first.");
  let file: File | null = null;
  try {
    const form = await request.formData();
    const f = form.get("file");
    file = f instanceof File ? f : null;
  } catch {
    return jsonError(400, "Expected a multipart upload with a 'file' field");
  }
  if (!file) return jsonError(400, "No file uploaded");
  if (file.size > MAX_UPLOAD_BYTES) return jsonError(413, "File too large (max 2 MB)");
  const kind = kindFor(file.name, file.type);
  if (!kind) return jsonError(415, "Unsupported file type. Upload .txt, .csv or .pdf.");
  const name = file.name.replace(/[^\w.\- ()]/g, "_").slice(0, 100);
  const bytes = Buffer.from(await file.arrayBuffer());

  let result: Pick<DocumentRecord, "docType" | "extraction" | "flags">;
  if (kind === "pdf") {
    if (bytes.subarray(0, 5).toString() !== "%PDF-") return jsonError(415, "That file is not a valid PDF.");
    result = aiStatus().enabled
      ? await extractPdfWithAi(name, bytes.toString("base64"))
      : {
          docType: "unknown",
          flags: [],
          extraction: { status: "not_extracted", method: "none", note: "PDF reading needs the AI provider (ANTHROPIC_API_KEY), which is not configured. The file was stored for reference only; enter its figures manually, or upload a .txt/.csv version.", fields: [] },
        };
  } else {
    const text = bytes.toString("utf8");
    if (text.includes("\u0000")) return jsonError(415, "That file does not look like text.");
    result = extractFromText(name, kind, text);
  }
  const doc: DocumentRecord = {
    id: newId("doc"),
    name,
    size: file.size,
    mime: file.type || kind,
    uploadedAt: new Date().toISOString(),
    ...result,
    review: "pending",
    appliedFields: [],
  };
  session.documents.unshift(doc);
  audit(session, "document_uploaded", "user", `Uploaded "${name}": ${doc.extraction.status.replace("_", " ")} (${doc.extraction.fields.length} field(s), ${doc.extraction.method.replace(/_/g, " ")})`);
  return NextResponse.json({ document: doc, state: stateView(session) });
}

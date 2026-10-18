export type Status = "OK" | "ERROR" | "WARNING" | "CAN'T CHECK" | "NOTE";

/** One checked line, as produced by the simulator (never by a model). */
export interface LineResult {
  index: number;
  text: string;
  label: string | null;
  kind: string;
  status: Status;
  available: number | null;
  used: number | null;
  made: number | null;
  stated: number | null;
  codes: string[];
  explanation: string;
  program_text: string;
  rows_made: number[];
}

export type Counts = Partial<Record<Status, number>>;

export interface CheckDone {
  counts: Counts;
  summary: string;
  backend: string;
  header: string;
}

export interface AppStatus {
  model: { name: string; ready: boolean; detail: string; local: boolean; demo?: boolean; command: string };
  photo_reader: { ready: boolean; detail: string; model: string };
}

export interface UploadResult {
  text: string;
  merge_wrapped: boolean;
  source: "text" | "pdf" | "photo";
  transcribed_by: string | null;
}

export interface RowAnswer {
  answer: string;
  result: Omit<LineResult, "text" | "rows_made"> | null;
}

export interface ApiError {
  message: string;
  command?: string;
}

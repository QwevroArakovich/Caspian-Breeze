import type { ReportStatus, ReportType } from "../api";

export type Filters = { statuses: ReportStatus[]; districtId: number | null; type: ReportType | ""; q: string };
export const OPEN: ReportStatus[] = ["new", "in_review", "planned"];

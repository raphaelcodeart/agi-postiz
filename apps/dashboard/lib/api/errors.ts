export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function parseErrorResponse(response: Response): Promise<ApiError> {
  let detail = response.statusText || "Request failed";
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body?.detail)) {
      // FastAPI/Pydantic validation error array
      detail = body.detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join("; ") || detail;
    }
  } catch {
    // response had no JSON body
  }
  return new ApiError(response.status, detail);
}

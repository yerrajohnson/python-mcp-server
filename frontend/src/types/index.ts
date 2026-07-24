export type SpecStatus =
  | 'uploaded'
  | 'parsing'
  | 'parsed'
  | 'parse_error'
  | 'generating'
  | 'generated'
  | 'error';

export type FileType = 'yaml' | 'yml' | 'json';

export type AuthType = 'apiKey' | 'bearer' | 'oauth2' | 'basic' | 'none';

export interface SpecificationSummary {
  id: string;
  name: string;
  version: string;
  file_type: FileType;
  upload_date: string;
  status: SpecStatus;
  error_message?: string | null;
  endpoint_count: number;
  auth_types: string[];
}

export interface AuthScheme {
  name: string;
  type: AuthType;
  scheme?: string | null;
  location?: string | null;
  param_name?: string | null;
  description?: string | null;
}

export interface EndpointInfo {
  operation_id?: string | null;
  method: string;
  path: string;
  summary?: string | null;
  description?: string | null;
  tags: string[];
  tool_name?: string | null;
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
  security?: Record<string, string[]>[];
}

export interface SpecInfo {
  title: string;
  version: string;
  description?: string | null;
  openapi_version?: string | null;
  servers: Record<string, unknown>[];
}

export interface ParsedSpec {
  info: SpecInfo;
  auth_schemes: AuthScheme[];
  endpoints: EndpointInfo[];
  tags: string[];
}

export interface Specification {
  id: string;
  name: string;
  version: string;
  file_type: FileType;
  original_filename: string;
  upload_date: string;
  status: SpecStatus;
  error_message?: string | null;
  file_path: string;
  parsed?: ParsedSpec | null;
}

export interface ParseResponse {
  spec_id: string;
  status: SpecStatus;
  info?: SpecInfo | null;
  auth_schemes: AuthScheme[];
  endpoints: EndpointInfo[];
  tags: string[];
  error_message?: string | null;
}

export interface GenerateRequest {
  spec_ids: string[];
  selected_endpoints: Record<string, string[]>;
  server_name: string;
  output_folder?: string | null;
}

export interface GenerateResponse {
  generation_id: string;
  server_name: string;
  tool_count: number;
  authentication: string[];
  selected_endpoints: string[];
  output_folder: string;
  status: string;
  files: string[];
  logs: string[];
}

export interface ApiError {
  error: string;
  details?: Record<string, unknown>;
}

export function endpointKey(ep: Pick<EndpointInfo, 'method' | 'path'>): string {
  return `${ep.method}:${ep.path}`;
}

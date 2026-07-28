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

export type McpServerStatus = 'stopped' | 'running' | 'error';

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

export interface LogicalGroupEndpoint {
  key: string;
  method: string;
  path: string;
  summary?: string | null;
  tool_name?: string | null;
  tags: string[];
}

export interface LogicalGroup {
  id: string;
  name: string;
  description?: string | null;
  endpoints: LogicalGroupEndpoint[];
}

export interface GeneratedServerPreview {
  temp_id: string;
  name: string;
  description?: string | null;
  server_url: string;
  port: number;
  authentication: string[];
  tool_count: number;
  tools: Array<{
    name: string;
    description: string;
    method: string;
    path: string;
  }>;
  output_folder: string;
  generation_id: string;
}

export interface WizardGenerateResponse {
  batch_id: string;
  servers: GeneratedServerPreview[];
  logs: string[];
}

export interface McpServerRecord {
  id: string;
  name: string;
  description?: string | null;
  spec_id: string;
  spec_name: string;
  tool_count: number;
  authentication: string[];
  server_url: string;
  port: number;
  status: McpServerStatus;
  created_date: string;
  generation_id: string;
  output_folder: string;
  tools: Array<Record<string, unknown>>;
  pid?: number | null;
  logical_group?: string | null;
  transport?: string;
  version?: string;
}

export interface TreeToolNode {
  id: string;
  name: string;
  description?: string | null;
  method?: string | null;
  path?: string | null;
  operation_id?: string | null;
  summary?: string | null;
  tags: string[];
  url?: string | null;
  base_url?: string | null;
  parameters: Array<Record<string, unknown>>;
  request_body?: Record<string, unknown> | null;
  responses: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  security: Array<Record<string, unknown>>;
  auth_schemes: Array<Record<string, unknown>>;
}

export interface TreeServerNode {
  id: string;
  name: string;
  description?: string | null;
  endpoint: string;
  port: number;
  status: McpServerStatus;
  authentication: string[];
  tool_count: number;
  created_date: string;
  transport: string;
  version: string;
  logical_group?: string | null;
  tools: TreeToolNode[];
}

export interface TreeSpecNode {
  id: string;
  name: string;
  version: string;
  description?: string | null;
  openapi_version?: string | null;
  base_urls: string[];
  auth_types: string[];
  endpoint_count: number;
  server_count: number;
  tool_count: number;
  upload_date?: string | null;
  servers: TreeServerNode[];
}

export interface McpTreeResponse {
  specifications: TreeSpecNode[];
}

export type TreeSelection =
  | { type: 'spec'; spec: TreeSpecNode }
  | { type: 'server'; spec: TreeSpecNode; server: TreeServerNode }
  | { type: 'tool'; spec: TreeSpecNode; server: TreeServerNode; tool: TreeToolNode };

export function endpointKey(ep: Pick<EndpointInfo, 'method' | 'path'>): string {
  return `${ep.method}:${ep.path}`;
}

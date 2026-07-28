import axios from 'axios';
import type {
  LogicalGroup,
  McpServerRecord,
  McpTreeResponse,
  ParseResponse,
  Specification,
  SpecificationSummary,
  WizardGenerateResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 180_000,
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const message =
      error.response?.data?.error ??
      error.message ??
      'Unexpected API error';
    return Promise.reject(new Error(message));
  },
);

export const specsApi = {
  list: async () => (await api.get<SpecificationSummary[]>('/specifications')).data,
  get: async (id: string) => (await api.get<Specification>(`/spec/${id}`)).data,
  upload: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return (await api.post<SpecificationSummary>('/upload-spec', form)).data;
  },
  remove: async (id: string) => (await api.delete(`/spec/${id}`)).data,
  getRaw: async (id: string) =>
    (await api.get<{ content: string; filename: string; file_type: string }>(`/spec/${id}/raw`)).data,
  parse: async (specId: string) =>
    (await api.post<ParseResponse>('/parse', { spec_id: specId })).data,
  generateMetadata: async (specId: string) =>
    (await api.post<ParseResponse>('/generate-metadata', { spec_id: specId })).data,
};

export const mcpServersApi = {
  list: async () => (await api.get<McpServerRecord[]>('/mcp-servers')).data,
  tree: async () => (await api.get<McpTreeResponse>('/mcp-servers/tree')).data,
  get: async (id: string) => (await api.get<McpServerRecord>(`/mcp-servers/${id}`)).data,
  update: async (id: string, body: { name?: string; description?: string }) =>
    (await api.patch<McpServerRecord>(`/mcp-servers/${id}`, body)).data,
  remove: async (id: string) => (await api.delete(`/mcp-servers/${id}`)).data,
  group: async (specId: string, selectedEndpoints: string[]) =>
    (
      await api.post<{ spec_id: string; groups: LogicalGroup[] }>('/mcp-servers/group', {
        spec_id: specId,
        selected_endpoints: selectedEndpoints,
      })
    ).data,
  wizardGenerate: async (specId: string, groups: LogicalGroup[]) =>
    (
      await api.post<WizardGenerateResponse>('/mcp-servers/wizard/generate', {
        spec_id: specId,
        groups,
      })
    ).data,
  wizardSave: async (batchId: string, servers: WizardGenerateResponse['servers']) =>
    (
      await api.post<McpServerRecord[]>('/mcp-servers/wizard/save', {
        batch_id: batchId,
        servers,
      })
    ).data,
  downloadUrl: (id: string) => `${API_BASE}/mcp-servers/${id}/download`,
  start: async (id: string) => (await api.post<McpServerRecord>(`/mcp-servers/${id}/start`)).data,
  stop: async (id: string) => (await api.post<McpServerRecord>(`/mcp-servers/${id}/stop`)).data,
};

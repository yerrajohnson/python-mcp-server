import axios from 'axios';
import type {
  GenerateRequest,
  GenerateResponse,
  ParseResponse,
  Specification,
  SpecificationSummary,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
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

export const generateApi = {
  generate: async (body: GenerateRequest) =>
    (await api.post<GenerateResponse>('/generate', body)).data,
  downloadUrl: (generationId: string) => `${API_BASE}/download/${generationId}`,
  run: async (generationId: string) =>
    (await api.post('/run', { generation_id: generationId })).data,
  stop: async (generationId: string) =>
    (await api.post(`/stop/${generationId}`)).data,
  get: async (generationId: string) =>
    (await api.get(`/generations/${generationId}`)).data,
};

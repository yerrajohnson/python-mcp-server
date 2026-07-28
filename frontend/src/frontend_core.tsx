import AddIcon from '@mui/icons-material/Add';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import BuildIcon from '@mui/icons-material/Build';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import DownloadIcon from '@mui/icons-material/Download';
import EditIcon from '@mui/icons-material/Edit';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FolderIcon from '@mui/icons-material/Folder';
import HubIcon from '@mui/icons-material/Hub';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import VisibilityIcon from '@mui/icons-material/Visibility';
import axios from 'axios';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  Container,
  CssBaseline,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  ThemeProvider,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import { createTheme } from '@mui/material/styles';
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReactNode, MouseEvent as ReactMouseEvent } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
  logical_group?: string | null;
  spec_slug?: string | null;
  server_slug?: string | null;
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
  spec_slug?: string | null;
  server_slug?: string | null;
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

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 180_000,
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const message = error.response?.data?.error ?? error.message ?? 'Unexpected API error';
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
  parse: async (specId: string) => (await api.post<ParseResponse>('/parse', { spec_id: specId })).data,
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

export const queryKeys = {
  specs: ['specifications'] as const,
  spec: (id: string) => ['specification', id] as const,
  mcpServers: ['mcp-servers'] as const,
  mcpTree: ['mcp-tree'] as const,
};

export function useSpecifications() {
  return useQuery({
    queryKey: queryKeys.specs,
    queryFn: specsApi.list,
  });
}

export function useSpecification(id: string | null) {
  return useQuery({
    queryKey: queryKeys.spec(id ?? ''),
    queryFn: () => specsApi.get(id!),
    enabled: Boolean(id),
  });
}

export function useUploadSpec() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.upload,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.specs }),
  });
}

export function useDeleteSpec() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.specs });
      qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
      qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
    },
  });
}

export function useParseSpec() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.parse,
    onSuccess: (_data, specId) => {
      qc.invalidateQueries({ queryKey: queryKeys.specs });
      qc.invalidateQueries({ queryKey: queryKeys.spec(specId) });
    },
  });
}

export function useGenerateMetadata() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.generateMetadata,
    onSuccess: (_data, specId) => {
      qc.invalidateQueries({ queryKey: queryKeys.specs });
      qc.invalidateQueries({ queryKey: queryKeys.spec(specId) });
    },
  });
}

export function useMcpServers() {
  return useQuery({
    queryKey: queryKeys.mcpServers,
    queryFn: mcpServersApi.list,
  });
}

export function useMcpTree() {
  return useQuery({
    queryKey: queryKeys.mcpTree,
    queryFn: mcpServersApi.tree,
  });
}

export function useGroupEndpoints() {
  return useMutation({
    mutationFn: ({ specId, keys }: { specId: string; keys: string[] }) =>
      mcpServersApi.group(specId, keys),
  });
}

export function useWizardGenerate() {
  return useMutation({
    mutationFn: ({ specId, groups }: { specId: string; groups: LogicalGroup[] }) =>
      mcpServersApi.wizardGenerate(specId, groups),
  });
}

export function useWizardSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      batchId,
      servers,
    }: {
      batchId: string;
      servers: Parameters<typeof mcpServersApi.wizardSave>[1];
    }) => mcpServersApi.wizardSave(batchId, servers),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
      qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
    },
  });
}

function patchServerStatusInTree(
  tree: McpTreeResponse | undefined,
  serverId: string,
  status: McpServerStatus,
): McpTreeResponse | undefined {
  if (!tree) return tree;
  return {
    ...tree,
    specifications: tree.specifications.map((spec) => ({
      ...spec,
      servers: spec.servers.map((server) =>
        server.id === serverId ? { ...server, status } : server,
      ),
    })),
  };
}

function syncServerStatus(qc: ReturnType<typeof useQueryClient>, record: McpServerRecord) {
  qc.setQueryData<McpTreeResponse>(queryKeys.mcpTree, (prev) =>
    patchServerStatusInTree(prev, record.id, record.status),
  );
  qc.setQueryData<McpServerRecord[]>(queryKeys.mcpServers, (prev) =>
    prev?.map((server) => (server.id === record.id ? { ...server, status: record.status } : server)),
  );
  void qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
  void qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
}

export function useMcpServerActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
    void qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
  };
  return {
    start: useMutation({
      mutationFn: mcpServersApi.start,
      onSuccess: (record) => syncServerStatus(qc, record),
    }),
    stop: useMutation({
      mutationFn: mcpServersApi.stop,
      onSuccess: (record) => syncServerStatus(qc, record),
    }),
    remove: useMutation({
      mutationFn: mcpServersApi.remove,
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string; name?: string; description?: string }) =>
        mcpServersApi.update(id, body),
      onSuccess: invalidate,
    }),
  };
}

export const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1565c0' },
    secondary: { main: '#00838f' },
    background: { default: '#f5f7fa', paper: '#ffffff' },
  },
  typography: {
    fontFamily: '"IBM Plex Sans", "Segoe UI", Roboto, sans-serif',
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600 },
      },
    },
  },
});

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#64b5f6' },
    secondary: { main: '#4dd0e1' },
    background: { default: '#0f1419', paper: '#1a2332' },
  },
  typography: {
    fontFamily: '"IBM Plex Sans", "Segoe UI", Roboto, sans-serif',
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600 },
      },
    },
  },
});

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
});

export function JsonViewer({ value, title }: { value: unknown; title?: string }) {
  const text = JSON.stringify(value ?? {}, null, 2);
  return (
    <Box sx={{ mb: 2 }}>
      {title && (
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {title}
        </Typography>
      )}
      <Box
        component="pre"
        sx={{
          m: 0,
          p: 1.5,
          borderRadius: 1,
          bgcolor: 'action.hover',
          overflow: 'auto',
          maxHeight: 280,
          fontSize: 12,
          fontFamily: '"IBM Plex Mono", Consolas, monospace',
          lineHeight: 1.45,
        }}
      >
        {text}
      </Box>
    </Box>
  );
}

const colorMap: Record<
  SpecStatus,
  'default' | 'info' | 'success' | 'warning' | 'error' | 'primary' | 'secondary'
> = {
  uploaded: 'default',
  parsing: 'info',
  parsed: 'success',
  parse_error: 'error',
  generating: 'warning',
  generated: 'primary',
  error: 'error',
};

export function StatusChip({ status }: { status: SpecStatus }) {
  return (
    <Chip
      size="small"
      label={status.replace('_', ' ')}
      color={colorMap[status]}
      sx={{ textTransform: 'capitalize' }}
    />
  );
}

const ACCEPT = '.yaml,.yml,.json';

export function SpecUploadZone() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const upload = useUploadSpec();

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      setLocalError(null);
      const file = files[0];
      if (!file) return;
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (!ext || !['yaml', 'yml', 'json'].includes(ext)) {
        setLocalError('Only YAML (.yaml, .yml) and JSON (.json) files are supported.');
        return;
      }
      try {
        await upload.mutateAsync(file);
      } catch (err) {
        setLocalError(err instanceof Error ? err.message : 'Upload failed');
      }
    },
    [upload],
  );

  return (
    <Paper
      variant="outlined"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        void handleFiles(e.dataTransfer.files);
      }}
      sx={{
        p: 4,
        textAlign: 'center',
        borderStyle: 'dashed',
        borderWidth: 2,
        borderColor: dragOver ? 'primary.main' : 'divider',
        bgcolor: dragOver ? 'action.hover' : 'background.paper',
        transition: 'all 0.15s ease',
      }}
    >
      <CloudUploadIcon color="primary" sx={{ fontSize: 48, mb: 1 }} />
      <Typography variant="h6" gutterBottom>
        Upload OpenAPI Specification
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Drag & drop a YAML or JSON file, or click to browse
      </Typography>
      <Button
        variant="contained"
        startIcon={upload.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
        disabled={upload.isPending}
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? 'Uploading…' : 'Select File'}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          if (e.target.files) void handleFiles(e.target.files);
          e.target.value = '';
        }}
      />
      {(localError || upload.isError) && (
        <Box sx={{ mt: 2 }}>
          <Alert severity="error">{localError ?? (upload.error as Error)?.message}</Alert>
        </Box>
      )}
      {upload.isSuccess && !localError && (
        <Box sx={{ mt: 2 }}>
          <Alert severity="success">Uploaded successfully — click Parse to validate.</Alert>
        </Box>
      )}
    </Paper>
  );
}

export function SpecsTable({ onView }: { onView: (spec: SpecificationSummary) => void }) {
  const { data, isLoading, error } = useSpecifications();
  const del = useDeleteSpec();
  const parse = useParseSpec();
  const meta = useGenerateMetadata();

  if (isLoading) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress />
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="error">{(error as Error).message}</Typography>
      </Paper>
    );
  }

  if (!data?.length) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="text.secondary">No specifications uploaded yet.</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Spec Name</TableCell>
            <TableCell>Version</TableCell>
            <TableCell>File Type</TableCell>
            <TableCell>Upload Date</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((spec) => {
            const busy =
              (parse.isPending && parse.variables === spec.id) ||
              (meta.isPending && meta.variables === spec.id) ||
              (del.isPending && del.variables === spec.id);
            return (
              <TableRow key={spec.id} hover>
                <TableCell>
                  <Typography sx={{ fontWeight: 600 }}>{spec.name}</Typography>
                  {spec.error_message && (
                    <Typography variant="caption" color="error" sx={{ display: 'block' }}>
                      {spec.error_message}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{spec.version}</TableCell>
                <TableCell sx={{ textTransform: 'uppercase' }}>{spec.file_type}</TableCell>
                <TableCell>{new Date(spec.upload_date).toLocaleString()}</TableCell>
                <TableCell>
                  <StatusChip status={spec.status} />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="View">
                    <IconButton size="small" onClick={() => onView(spec)} disabled={busy}>
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Parse">
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => parse.mutate(spec.id)}
                      disabled={busy}
                    >
                      {parse.isPending && parse.variables === spec.id ? (
                        <CircularProgress size={16} />
                      ) : (
                        <PlayArrowIcon fontSize="small" />
                      )}
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Generate Metadata">
                    <IconButton
                      size="small"
                      color="secondary"
                      onClick={() => meta.mutate(spec.id)}
                      disabled={busy || spec.status === 'uploaded'}
                    >
                      {meta.isPending && meta.variables === spec.id ? (
                        <CircularProgress size={16} />
                      ) : (
                        <AutoFixHighIcon fontSize="small" />
                      )}
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        if (
                          confirm(
                            `Delete "${spec.name}"? This will also remove all MCP servers generated from this spec.`,
                          )
                        ) {
                          del.mutate(spec.id);
                        }
                      }}
                      disabled={busy}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export function SpecViewerDialog({ specId, onClose }: { specId: string | null; onClose: () => void }) {
  const [tab, setTab] = useState(0);
  const { data: spec } = useSpecification(specId);
  const { data: raw } = useQuery({
    queryKey: ['raw', specId],
    queryFn: () => specsApi.getRaw(specId!),
    enabled: Boolean(specId),
  });

  return (
    <Dialog open={Boolean(specId)} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {spec?.name ?? 'Specification'}
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Overview" />
          <Tab label="Source" />
          <Tab label="Endpoints" />
        </Tabs>

        {tab === 0 && spec && (
          <Stack spacing={1}>
            <Typography>
              <strong>Version:</strong> {spec.version}
            </Typography>
            <Typography>
              <strong>OpenAPI:</strong> {spec.parsed?.info.openapi_version ?? '—'}
            </Typography>
            <Typography>
              <strong>Status:</strong> {spec.status}
            </Typography>
            {spec.error_message && <Typography color="error">{spec.error_message}</Typography>}
            <Box>
              <Typography gutterBottom sx={{ fontWeight: 600 }}>
                Auth
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 1 }}>
                {(spec.parsed?.auth_schemes ?? []).map((auth) => (
                  <Chip key={auth.name} label={`${auth.name} (${auth.type})`} size="small" />
                ))}
              </Box>
            </Box>
          </Stack>
        )}

        {tab === 1 && (
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2,
              bgcolor: 'action.hover',
              borderRadius: 1,
              overflow: 'auto',
              maxHeight: 480,
              fontSize: 12,
              fontFamily: '"IBM Plex Mono", Consolas, monospace',
            }}
          >
            {raw?.content ?? 'Loading…'}
          </Box>
        )}

        {tab === 2 && (
          <Stack spacing={1}>
            {(spec?.parsed?.endpoints ?? []).map((ep) => (
              <Box key={`${ep.method}:${ep.path}`} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <Chip label={ep.method} size="small" color="primary" />
                <Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>{ep.path}</Typography>
                <Typography color="text.secondary" sx={{ fontSize: 13 }}>
                  {ep.summary || ep.tool_name}
                </Typography>
              </Box>
            ))}
            {!spec?.parsed?.endpoints?.length && (
              <Typography color="text.secondary">Parse the spec to see endpoints.</Typography>
            )}
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
}

const STEPS = [
  'Choose Specification',
  'Choose Endpoints',
  'Logical Groups',
  'Generate MCP Servers',
  'Review & Save',
];

export function GenerateWizard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [specId, setSpecId] = useState<string | null>(null);
  const [searchSpec, setSearchSpec] = useState('');
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [endpointSearch, setEndpointSearch] = useState('');
  const [expandedTags, setExpandedTags] = useState<Record<string, boolean>>({});
  const [groups, setGroups] = useState<LogicalGroup[]>([]);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [servers, setServers] = useState<GeneratedServerPreview[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: specs = [] } = useSpecifications();
  const { data: specDetail } = useSpecification(specId);
  const groupMutation = useGroupEndpoints();
  const generateMutation = useWizardGenerate();
  const saveMutation = useWizardSave();

  const filteredSpecs = useMemo(() => {
    const q = searchSpec.toLowerCase();
    return specs.filter(
      (s) =>
        (s.status === 'parsed' || s.status === 'generated' || s.status === 'uploaded') &&
        (!q || s.name.toLowerCase().includes(q) || s.version.toLowerCase().includes(q)),
    );
  }, [specs, searchSpec]);

  const authLabel = useMemo(() => {
    const types = specDetail?.parsed?.auth_schemes?.map((a) => a.type) ?? [];
    return types.length ? types.join(', ') : 'none';
  }, [specDetail]);

  const endpointsByTag = useMemo(() => {
    const endpoints = specDetail?.parsed?.endpoints ?? [];
    const map: Record<string, typeof endpoints> = {};
    const q = endpointSearch.toLowerCase();
    for (const ep of endpoints) {
      if (
        q &&
        !ep.path.toLowerCase().includes(q) &&
        !(ep.summary ?? '').toLowerCase().includes(q) &&
        !(ep.tool_name ?? '').toLowerCase().includes(q)
      ) {
        continue;
      }
      const tag = ep.tags[0] || 'default';
      (map[tag] ??= []).push(ep);
    }
    return map;
  }, [specDetail, endpointSearch]);

  const reset = () => {
    setStep(0);
    setSpecId(null);
    setSearchSpec('');
    setSelectedKeys(new Set());
    setEndpointSearch('');
    setExpandedTags({});
    setGroups([]);
    setBatchId(null);
    setServers([]);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const ensureParsed = async (id: string) => {
    const current = await specsApi.get(id);
    if (!current.parsed) {
      const parsed = await specsApi.parse(id);
      if (parsed.status === 'parse_error') {
        throw new Error(parsed.error_message || 'Failed to parse specification');
      }
    }
  };

  const goNextFromSpec = async () => {
    if (!specId) return;
    setError(null);
    try {
      await ensureParsed(specId);
      setSelectedKeys(new Set());
      setStep(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load endpoints');
    }
  };

  const goGenerateGroups = async () => {
    if (!specId || selectedKeys.size === 0) return;
    setError(null);
    try {
      const res = await groupMutation.mutateAsync({
        specId,
        keys: Array.from(selectedKeys),
      });
      setGroups(res.groups);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Grouping failed');
    }
  };

  const goGenerateServers = async () => {
    if (!specId || groups.length === 0) return;
    setError(null);
    try {
      const res = await generateMutation.mutateAsync({ specId, groups });
      setBatchId(res.batch_id);
      setServers(res.servers);
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed');
    }
  };

  const handleSave = async () => {
    if (!batchId) return;
    setError(null);
    try {
      await saveMutation.mutateAsync({ batchId, servers });
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    }
  };

  const toggleKey = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectTag = (tag: string, select: boolean) => {
    const eps = endpointsByTag[tag] ?? [];
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      for (const ep of eps) {
        const key = endpointKey(ep);
        if (select) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  };

  const allEndpointKeys = Object.values(endpointsByTag).flat().map(endpointKey);

  const renameGroup = (id: string, name: string) => {
    setGroups((prev) => prev.map((group) => (group.id === id ? { ...group, name } : group)));
  };

  const busy = groupMutation.isPending || generateMutation.isPending || saveMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
      <DialogTitle>Generate MCP Servers — Step {step + 1} of {STEPS.length}</DialogTitle>
      <DialogContent dividers>
        <Stepper activeStep={step} alternativeLabel sx={{ mb: 3 }}>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {busy && <LinearProgress sx={{ mb: 2 }} />}

        {step === 0 && (
          <StepChooseSpec
            specs={filteredSpecs}
            selectedId={specId}
            search={searchSpec}
            onSearch={setSearchSpec}
            onSelect={setSpecId}
          />
        )}

        {step === 1 && (
          <StepChooseEndpoints
            authLabel={authLabel}
            byTag={endpointsByTag}
            selectedKeys={selectedKeys}
            search={endpointSearch}
            expanded={expandedTags}
            onSearch={setEndpointSearch}
            onToggle={toggleKey}
            onSelectAll={(select) => setSelectedKeys(select ? new Set(allEndpointKeys) : new Set())}
            onSelectTag={selectTag}
            onExpand={(tag) =>
              setExpandedTags((prev) => ({ ...prev, [tag]: !(prev[tag] ?? true) }))
            }
          />
        )}

        {step === 2 && <StepLogicalGroups groups={groups} onRename={renameGroup} />}
        {step === 3 && <StepGeneratedServers servers={servers} />}
        {step === 4 && (
          <StepReview
            specName={specDetail?.parsed?.info.title ?? specDetail?.name ?? '—'}
            endpointCount={selectedKeys.size}
            groupCount={groups.length}
            servers={servers}
          />
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2, justifyContent: 'space-between' }}>
        <Button onClick={handleClose} disabled={busy}>
          Cancel
        </Button>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {step > 0 && (
            <Button onClick={() => setStep((s) => s - 1)} disabled={busy}>
              Previous
            </Button>
          )}
          {step === 0 && (
            <Button variant="contained" disabled={!specId || busy} onClick={() => void goNextFromSpec()}>
              Next
            </Button>
          )}
          {step === 1 && (
            <Button
              variant="contained"
              disabled={selectedKeys.size === 0 || busy}
              onClick={() => void goGenerateGroups()}
            >
              Generate Logical Groups
            </Button>
          )}
          {step === 2 && (
            <Button
              variant="contained"
              disabled={groups.length === 0 || busy}
              onClick={() => void goGenerateServers()}
              startIcon={generateMutation.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              Generate MCP Servers
            </Button>
          )}
          {step === 3 && (
            <Button variant="contained" onClick={() => setStep(4)} disabled={busy || servers.length === 0}>
              Next
            </Button>
          )}
          {step === 4 && (
            <Button
              variant="contained"
              onClick={() => void handleSave()}
              disabled={busy || !batchId}
              startIcon={saveMutation.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              Save
            </Button>
          )}
        </Box>
      </DialogActions>
    </Dialog>
  );
}

function StepChooseSpec({
  specs,
  selectedId,
  search,
  onSearch,
  onSelect,
}: {
  specs: SpecificationSummary[];
  selectedId: string | null;
  search: string;
  onSearch: (v: string) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Choose an uploaded OpenAPI specification. You will then select endpoints and generate MCP servers.
      </Typography>
      <TextField
        fullWidth
        size="small"
        placeholder="Search specifications…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        sx={{ mb: 2 }}
      />
      <Paper variant="outlined" sx={{ maxHeight: 360, overflow: 'auto' }}>
        <List dense>
          {specs.map((spec) => (
            <ListItemButton
              key={spec.id}
              selected={selectedId === spec.id}
              onClick={() => onSelect(spec.id)}
            >
              <ListItemText
                primary={spec.name}
                secondary={`v${spec.version} · ${spec.status} · ${new Date(spec.upload_date).toLocaleString()}`}
              />
            </ListItemButton>
          ))}
          {!specs.length && (
            <Box sx={{ p: 2 }}>
              <Typography color="text.secondary">No specifications found. Upload one in the Specs tab first.</Typography>
            </Box>
          )}
        </List>
      </Paper>
    </Box>
  );
}

function StepChooseEndpoints({
  authLabel,
  byTag,
  selectedKeys,
  search,
  expanded,
  onSearch,
  onToggle,
  onSelectAll,
  onSelectTag,
  onExpand,
}: {
  authLabel: string;
  byTag: Record<string, Array<{ method: string; path: string; summary?: string | null; tool_name?: string | null }>>;
  selectedKeys: Set<string>;
  search: string;
  expanded: Record<string, boolean>;
  onSearch: (v: string) => void;
  onToggle: (key: string) => void;
  onSelectAll: (select: boolean) => void;
  onSelectTag: (tag: string, select: boolean) => void;
  onExpand: (tag: string) => void;
}) {
  const total = Object.values(byTag).flat().length;
  return (
    <Box>
      <Typography sx={{ mb: 1 }}>
        Authentication detected: <Chip size="small" label={authLabel} />
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2, alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder="Search endpoints…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          sx={{ flex: 1, minWidth: 200 }}
        />
        <Button size="small" onClick={() => onSelectAll(true)}>
          Select All ({total})
        </Button>
        <Button size="small" onClick={() => onSelectAll(false)}>
          Deselect All
        </Button>
      </Box>
      <Box sx={{ maxHeight: 380, overflow: 'auto' }}>
        {Object.entries(byTag).map(([tag, eps]) => {
          const open = expanded[tag] ?? true;
          const selectedCount = eps.filter((ep) => selectedKeys.has(endpointKey(ep))).length;
          return (
            <Paper key={tag} variant="outlined" sx={{ mb: 1, p: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <IconButton size="small" onClick={() => onExpand(tag)}>
                  {open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
                <Typography sx={{ fontWeight: 600, flex: 1 }}>
                  {tag} ({selectedCount}/{eps.length})
                </Typography>
                <Button size="small" onClick={() => onSelectTag(tag, true)}>
                  Select tag
                </Button>
                <Button size="small" onClick={() => onSelectTag(tag, false)}>
                  Clear
                </Button>
              </Box>
              <Collapse in={open}>
                {eps.map((ep) => {
                  const key = endpointKey(ep);
                  return (
                    <FormControlLabel
                      key={key}
                      sx={{ display: 'flex', ml: 1 }}
                      control={
                        <Checkbox
                          size="small"
                          checked={selectedKeys.has(key)}
                          onChange={() => onToggle(key)}
                        />
                      }
                      label={
                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                          <Chip label={ep.method} size="small" sx={{ minWidth: 56 }} />
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            {ep.path}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {ep.summary || ep.tool_name}
                          </Typography>
                        </Box>
                      }
                    />
                  );
                })}
              </Collapse>
            </Paper>
          );
        })}
      </Box>
    </Box>
  );
}

function StepLogicalGroups({
  groups,
  onRename,
}: {
  groups: LogicalGroup[];
  onRename: (id: string, name: string) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(groups[0]?.id ?? null);
  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Review logical groups. Rename groups before generating MCP servers. Each group becomes one MCP server.
      </Typography>
      {groups.map((group) => (
        <Paper key={group.id} variant="outlined" sx={{ mb: 1, p: 1.5 }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <TextField
              size="small"
              value={group.name}
              onChange={(e) => onRename(group.id, e.target.value)}
              sx={{ flex: 1 }}
            />
            <Chip size="small" label={`${group.endpoints.length} endpoints`} />
            <IconButton size="small" onClick={() => setOpenId(openId === group.id ? null : group.id)}>
              {openId === group.id ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Box>
          {group.description && (
            <Typography variant="caption" color="text.secondary">
              {group.description}
            </Typography>
          )}
          <Collapse in={openId === group.id}>
            <Box sx={{ mt: 1 }}>
              {group.endpoints.map((ep) => (
                <Box key={ep.key} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.5 }}>
                  <Chip label={ep.method} size="small" />
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {ep.path}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {ep.summary || ep.tool_name}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Collapse>
        </Paper>
      ))}
    </Box>
  );
}

function StepGeneratedServers({ servers }: { servers: GeneratedServerPreview[] }) {
  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Generated {servers.length} MCP server(s). Review tools and URLs, then continue.
      </Typography>
      {servers.map((server) => (
        <Paper key={server.temp_id} variant="outlined" sx={{ p: 2, mb: 1.5 }}>
          <Typography sx={{ fontWeight: 700 }}>{server.name}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {server.description}
          </Typography>
          <Typography variant="body2">
            <strong>URL:</strong>{' '}
            <Box component="span" sx={{ fontFamily: 'monospace' }}>
              {server.server_url}
            </Box>
          </Typography>
          <Typography variant="body2">
            <strong>Auth:</strong> {server.authentication.join(', ') || 'none'}
          </Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>Tools:</strong> {server.tool_count}
          </Typography>
          {server.tools.map((tool) => (
            <Box key={tool.name} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.25 }}>
              <Chip label={tool.method} size="small" color="success" />
              <Typography variant="body2">{tool.name}</Typography>
            </Box>
          ))}
        </Paper>
      ))}
    </Box>
  );
}

function StepReview({
  specName,
  endpointCount,
  groupCount,
  servers,
}: {
  specName: string;
  endpointCount: number;
  groupCount: number;
  servers: GeneratedServerPreview[];
}) {
  return (
    <Stack spacing={1}>
      <Typography>
        <strong>Specification:</strong> {specName}
      </Typography>
      <Typography>
        <strong>Selected endpoints:</strong> {endpointCount}
      </Typography>
      <Typography>
        <strong>Logical groups:</strong> {groupCount}
      </Typography>
      <Typography>
        <strong>MCP servers:</strong> {servers.length}
      </Typography>
      {servers.map((server) => (
        <Paper key={server.temp_id} variant="outlined" sx={{ p: 1.5 }}>
          <Typography sx={{ fontWeight: 600 }}>{server.name}</Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
            {server.server_url}
          </Typography>
          <Typography variant="body2">
            {server.tool_count} tools · auth: {server.authentication.join(', ') || 'none'}
          </Typography>
        </Paper>
      ))}
    </Stack>
  );
}

export function McpServersTable({
  onView,
  onEdit,
}: {
  onView: (server: McpServerRecord) => void;
  onEdit: (server: McpServerRecord) => void;
}) {
  const { data = [], isLoading, error } = useMcpServers();
  const actions = useMcpServerActions();

  if (isLoading) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress />
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="error">{(error as Error).message}</Typography>
      </Paper>
    );
  }

  if (!data.length) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <Typography color="text.secondary">
          No MCP servers yet. Click <strong>Generate MCP Server</strong> to start the wizard.
        </Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>MCP Server Name</TableCell>
            <TableCell>Source Specification</TableCell>
            <TableCell>Tools</TableCell>
            <TableCell>Auth</TableCell>
            <TableCell>Server URL</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Created</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((server) => {
            const busy =
              (actions.start.isPending && actions.start.variables === server.id) ||
              (actions.stop.isPending && actions.stop.variables === server.id) ||
              (actions.remove.isPending && actions.remove.variables === server.id);
            return (
              <TableRow key={server.id} hover>
                <TableCell>
                  <Typography sx={{ fontWeight: 600 }}>{server.name}</Typography>
                </TableCell>
                <TableCell>{server.spec_name}</TableCell>
                <TableCell>{server.tool_count}</TableCell>
                <TableCell>{server.authentication.join(', ') || 'none'}</TableCell>
                <TableCell>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {server.server_url}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={server.status}
                    color={server.status === 'running' ? 'success' : 'default'}
                    sx={{ textTransform: 'capitalize' }}
                  />
                </TableCell>
                <TableCell>{new Date(server.created_date).toLocaleString()}</TableCell>
                <TableCell align="right">
                  <Tooltip title="View">
                    <IconButton size="small" onClick={() => onView(server)} disabled={busy}>
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Edit">
                    <IconButton size="small" onClick={() => onEdit(server)} disabled={busy}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Download">
                    <IconButton
                      size="small"
                      onClick={() => window.open(mcpServersApi.downloadUrl(server.id), '_blank')}
                      disabled={busy}
                    >
                      <DownloadIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  {server.status === 'running' ? (
                    <Tooltip title="Stop">
                      <IconButton
                        size="small"
                        color="warning"
                        onClick={() => actions.stop.mutate(server.id)}
                        disabled={busy}
                      >
                        <StopIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  ) : (
                    <Tooltip title="Start">
                      <IconButton
                        size="small"
                        color="success"
                        onClick={() => actions.start.mutate(server.id)}
                        disabled={busy}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  <Tooltip title="Delete">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        if (
                          confirm(
                            `Delete "${server.name}" and its ${server.tool_count} tool(s)? This cannot be undone.`,
                          )
                        ) {
                          actions.remove.mutate(server.id);
                        }
                      }}
                      disabled={busy}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

const EXPANDED_KEY = 'mcp-tree-expanded';

function loadExpanded(): Set<string> {
  try {
    const raw = localStorage.getItem(EXPANDED_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function saveExpanded(set: Set<string>) {
  localStorage.setItem(EXPANDED_KEY, JSON.stringify(Array.from(set)));
}

export function McpTreeNav({
  specifications,
  loading,
  selection,
  onSelect,
}: {
  specifications: TreeSpecNode[];
  loading?: boolean;
  selection: TreeSelection | null;
  onSelect: (sel: TreeSelection) => void;
}) {
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(() => loadExpanded());

  useEffect(() => {
    saveExpanded(expanded);
  }, [expanded]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return specifications;

    return specifications
      .map((spec) => {
        const specMatch = spec.name.toLowerCase().includes(q);
        const servers = spec.servers
          .map((server) => {
            const serverMatch = server.name.toLowerCase().includes(q);
            const tools = server.tools.filter(
              (tool) =>
                tool.name.toLowerCase().includes(q) ||
                (tool.path ?? '').toLowerCase().includes(q) ||
                (tool.description ?? '').toLowerCase().includes(q),
            );
            if (specMatch || serverMatch || tools.length) {
              return {
                ...server,
                tools: specMatch || serverMatch ? server.tools : tools,
              };
            }
            return null;
          })
          .filter(Boolean) as TreeSpecNode['servers'];

        if (specMatch || servers.length) {
          return { ...spec, servers: specMatch ? spec.servers : servers };
        }
        return null;
      })
      .filter(Boolean) as TreeSpecNode[];
  }, [specifications, query]);

  const toggle = (id: string, e?: ReactMouseEvent) => {
    e?.stopPropagation();
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const ensureExpanded = (...ids: string[]) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  };

  const selectedKey =
    selection?.type === 'spec'
      ? `spec:${selection.spec.id}`
      : selection?.type === 'server'
        ? `server:${selection.server.id}`
        : selection?.type === 'tool'
          ? `tool:${selection.server.id}:${selection.tool.id}`
          : null;

  if (loading) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TextField
        size="small"
        placeholder="Search specs, servers, tools…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        sx={{ m: 1.5, mb: 1 }}
      />
      <List dense sx={{ flex: 1, overflow: 'auto', py: 0 }}>
        {!filtered.length && (
          <Typography color="text.secondary" sx={{ px: 2, py: 1 }} variant="body2">
            No MCP servers yet. Generate one to populate the tree.
          </Typography>
        )}
        {filtered.map((spec) => {
          const specKey = `spec:${spec.id}`;
          const specOpen = expanded.has(specKey) || Boolean(query);
          return (
            <Box key={spec.id}>
              <ListItemButton
                selected={selectedKey === specKey}
                onClick={() => {
                  ensureExpanded(specKey);
                  onSelect({ type: 'spec', spec });
                }}
                sx={{ py: 0.75 }}
              >
                <IconButton size="small" onClick={(e) => toggle(specKey, e)} sx={{ mr: 0.5 }}>
                  {specOpen ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
                </IconButton>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  <FolderIcon fontSize="small" color="primary" />
                </ListItemIcon>
                <ListItemText
                  primary={spec.name}
                  secondary={`${spec.server_count} servers · ${spec.tool_count} tools`}
                  slotProps={{ primary: { sx: { fontWeight: 700, fontSize: 14 } } }}
                />
              </ListItemButton>

              <Collapse in={specOpen} timeout="auto" unmountOnExit>
                {spec.servers.map((server) => {
                  const serverKey = `server:${server.id}`;
                  const serverOpen = expanded.has(serverKey) || Boolean(query);
                  return (
                    <Box key={server.id}>
                      <ListItemButton
                        selected={selectedKey === serverKey}
                        onClick={() => {
                          ensureExpanded(specKey, serverKey);
                          onSelect({ type: 'server', spec, server });
                        }}
                        sx={{ pl: 4, py: 0.5 }}
                      >
                        <IconButton size="small" onClick={(e) => toggle(serverKey, e)} sx={{ mr: 0.5 }}>
                          {serverOpen ? (
                            <ExpandMoreIcon fontSize="small" />
                          ) : (
                            <ChevronRightIcon fontSize="small" />
                          )}
                        </IconButton>
                        <ListItemIcon sx={{ minWidth: 28 }}>
                          <HubIcon fontSize="small" color="secondary" />
                        </ListItemIcon>
                        <ListItemText
                          primary={server.name}
                          secondary={
                            <Chip
                              size="small"
                              label={server.status}
                              color={server.status === 'running' ? 'success' : 'default'}
                              sx={{ height: 18, fontSize: 10, mt: 0.25 }}
                            />
                          }
                          slotProps={{ primary: { sx: { fontSize: 13, fontWeight: 600 } } }}
                        />
                      </ListItemButton>

                      <Collapse in={serverOpen} timeout="auto" unmountOnExit>
                        {server.tools.map((tool) => {
                          const toolKey = `tool:${server.id}:${tool.id}`;
                          return (
                            <ListItemButton
                              key={toolKey}
                              selected={selectedKey === toolKey}
                              onClick={() => {
                                ensureExpanded(specKey, serverKey);
                                onSelect({ type: 'tool', spec, server, tool });
                              }}
                              sx={{ pl: 8, py: 0.35 }}
                            >
                              <ListItemIcon sx={{ minWidth: 28 }}>
                                <BuildIcon fontSize="small" />
                              </ListItemIcon>
                              <ListItemText
                                primary={tool.name}
                                secondary={tool.method ? `${tool.method} ${tool.path}` : undefined}
                                slotProps={{
                                  primary: { sx: { fontSize: 12.5 } },
                                  secondary: { sx: { fontSize: 11, fontFamily: 'monospace' } },
                                }}
                              />
                            </ListItemButton>
                          );
                        })}
                      </Collapse>
                    </Box>
                  );
                })}
              </Collapse>
              <Box sx={{ borderBottom: 1, borderColor: 'divider', mx: 1.5, my: 0.5 }} />
            </Box>
          );
        })}
      </List>
    </Box>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box sx={{ mb: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 1, fontSize: 16 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, py: 0.4 }}>
      <Typography variant="body2" sx={{ minWidth: 160, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ flex: 1 }}>
        {value || '—'}
      </Typography>
    </Box>
  );
}

export function SpecDetailPanel({ spec }: { spec: TreeSpecNode }) {
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        {spec.name}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        OpenAPI Specification
      </Typography>
      <Section title="Details">
        <Row label="Name" value={spec.name} />
        <Row label="Version" value={spec.version} />
        <Row label="Description" value={spec.description} />
        <Row label="OpenAPI Version" value={spec.openapi_version} />
        <Row
          label="Base URL(s)"
          value={
            spec.base_urls.length
              ? spec.base_urls.map((url) => (
                  <Typography key={url} sx={{ fontFamily: 'monospace', fontSize: 13 }}>
                    {url}
                  </Typography>
                ))
              : '—'
          }
        />
        <Row
          label="Authentication"
          value={
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {(spec.auth_types.length ? spec.auth_types : ['none']).map((auth) => (
                <Chip key={auth} size="small" label={auth} />
              ))}
            </Box>
          }
        />
        <Row label="Endpoints" value={String(spec.endpoint_count)} />
        <Row label="MCP Servers" value={String(spec.server_count)} />
        <Row label="Total Tools" value={String(spec.tool_count)} />
        <Row
          label="Upload Date"
          value={spec.upload_date ? new Date(spec.upload_date).toLocaleString() : '—'}
        />
      </Section>
    </Box>
  );
}

export function ServerDetailPanel({
  spec,
  server,
}: {
  spec: TreeSpecNode;
  server: TreeServerNode;
}) {
  const categories = Array.from(new Set(server.tools.flatMap((tool) => tool.tags))).filter(Boolean);

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        {server.name}
      </Typography>
      <Chip
        size="small"
        label={server.status}
        color={server.status === 'running' ? 'success' : 'default'}
        sx={{ mb: 2, textTransform: 'capitalize' }}
      />

      <Section title="General Information">
        <Row label="Server Name" value={server.name} />
        <Row label="Description" value={server.description} />
        <Row label="Source Specification" value={spec.name} />
        <Row label="Server Version" value={server.version} />
        <Row label="Authentication" value={server.authentication.join(', ') || 'none'} />
        <Row
          label="Client auth"
          value="Set Authorization / X-API-Key on Postman requests to this MCP URL; they are forwarded to the upstream API when tools run."
        />
        <Row label="Number of Tools" value={String(server.tool_count)} />
        <Row label="Status" value={server.status} />
        <Row label="Logical Group" value={server.logical_group} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Endpoint Information">
        <Row
          label="MCP Endpoint URL"
          value={<Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>{server.endpoint}</Typography>}
        />
        <Row label="Transport Type" value={(server.transport || 'streamable-http').toUpperCase()} />
        <Row label="Health Status" value={server.status === 'running' ? 'Healthy / Running' : 'Stopped'} />
        <Row label="Created Date" value={new Date(server.created_date).toLocaleString()} />
        <Row label="Port" value="shared (single FastAPI app)" />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Tools Summary">
        <Row label="Total Tools" value={String(server.tool_count)} />
        <Row
          label="Tool Categories"
          value={
            categories.length ? (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {categories.map((category) => (
                  <Chip key={category} size="small" label={category} />
                ))}
              </Box>
            ) : (
              '—'
            )
          }
        />
        <Box sx={{ mt: 1 }}>
          {server.tools.map((tool) => (
            <Box key={tool.id} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.4 }}>
              {tool.method && <Chip size="small" label={tool.method} color="primary" />}
              <Typography variant="body2">{tool.name}</Typography>
            </Box>
          ))}
        </Box>
      </Section>
    </Box>
  );
}

function getParamField(param: Record<string, unknown>, key: string): string | undefined {
  const value = param[key];
  return typeof value === 'string' ? value : undefined;
}

export function ToolDetailPanel({
  server,
  tool,
}: {
  server: TreeServerNode;
  tool: TreeToolNode;
}) {
  const pathParams = tool.parameters.filter((param) => {
    const location = getParamField(param, 'location') ?? getParamField(param, 'in');
    return location === 'path';
  });
  const queryParams = tool.parameters.filter((param) => {
    const location = getParamField(param, 'location') ?? getParamField(param, 'in');
    return location === 'query';
  });
  const headerParams = tool.parameters.filter((param) => {
    const location = getParamField(param, 'location') ?? getParamField(param, 'in');
    return location === 'header';
  });
  const primaryAuth = tool.auth_schemes[0] as Record<string, unknown> | undefined;

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        {tool.name}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Tool in {server.name}
      </Typography>

      <Section title="General Information">
        <Row label="Tool Name" value={tool.name} />
        <Row label="Description" value={tool.description} />
        <Row label="HTTP Method" value={tool.method} />
        <Row
          label="API Path"
          value={<Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>{tool.path}</Typography>}
        />
        <Row label="Operation ID" value={tool.operation_id} />
        <Row
          label="Tags"
          value={
            tool.tags.length ? (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {tool.tags.map((tag) => (
                  <Chip key={tag} size="small" label={tag} />
                ))}
              </Box>
            ) : (
              '—'
            )
          }
        />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Authentication">
        <Row
          label="Authentication Type"
          value={primaryAuth?.type ? String(primaryAuth.type) : server.authentication.join(', ') || 'none'}
        />
        <Row label="Security Scheme" value={primaryAuth ? String(primaryAuth.name ?? '—') : '—'} />
        <Row label="API Key Location" value={primaryAuth?.location ? String(primaryAuth.location) : '—'} />
        <Row label="Required Scopes" value={tool.security.length ? JSON.stringify(tool.security) : '—'} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Request Details">
        <Row
          label="Endpoint URL"
          value={
            <Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>
              {tool.url || `${tool.base_url ?? ''}${tool.path ?? ''}` || '—'}
            </Typography>
          }
        />
        <JsonViewer title="Headers (parameters)" value={headerParams} />
        <JsonViewer title="Query Parameters" value={queryParams} />
        <JsonViewer title="Path Parameters" value={pathParams} />
        <JsonViewer title="Request Body" value={tool.request_body ?? {}} />
        <JsonViewer title="Input Schema" value={tool.input_schema} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Response Details">
        <JsonViewer title="Responses / Status Codes" value={tool.responses} />
        <JsonViewer title="Output Schema" value={tool.output_schema} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="MCP Information">
        <Row label="Generated Tool Name" value={tool.name} />
        <Row label="Tool Description" value={tool.description} />
        <JsonViewer title="MCP Input Schema" value={tool.input_schema} />
        <JsonViewer title="MCP Output Schema" value={tool.output_schema} />
      </Section>
    </Box>
  );
}

export function EmptyDetailPanel() {
  return (
    <Box
      sx={{
        height: '100%',
        minHeight: 360,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        color: 'text.secondary',
        textAlign: 'center',
        p: 4,
      }}
    >
      <HubIconPlaceholder />
      <Typography variant="h6" sx={{ mt: 1 }}>
        Select a server or tool to view details
      </Typography>
      <Typography variant="body2">
        Choose a specification, MCP server, or tool from the tree.
      </Typography>
    </Box>
  );
}

function HubIconPlaceholder() {
  return (
    <Box
      sx={{
        width: 72,
        height: 72,
        borderRadius: 2,
        bgcolor: 'action.hover',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 32,
      }}
    >
      ⌂
    </Box>
  );
}

type SelectionRef =
  | { type: 'spec'; specId: string }
  | { type: 'server'; specId: string; serverId: string }
  | { type: 'tool'; specId: string; serverId: string; toolId: string };

function toSelectionRef(sel: TreeSelection): SelectionRef {
  if (sel.type === 'spec') return { type: 'spec', specId: sel.spec.id };
  if (sel.type === 'server') {
    return { type: 'server', specId: sel.spec.id, serverId: sel.server.id };
  }
  return {
    type: 'tool',
    specId: sel.spec.id,
    serverId: sel.server.id,
    toolId: sel.tool.id,
  };
}

function resolveSelection(specs: TreeSpecNode[], ref: SelectionRef | null): TreeSelection | null {
  if (!ref) return null;
  const spec = specs.find((item) => item.id === ref.specId);
  if (!spec) return null;
  if (ref.type === 'spec') return { type: 'spec', spec };

  const server = spec.servers.find((item) => item.id === ref.serverId);
  if (!server) return null;
  if (ref.type === 'server') return { type: 'server', spec, server };

  const tool = server.tools.find((item) => item.id === ref.toolId);
  if (!tool) return null;
  return { type: 'tool', spec, server, tool };
}

export function McpServersPage() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selectionRef, setSelectionRef] = useState<SelectionRef | null>(null);
  const { data, isLoading, error } = useMcpTree();
  const actions = useMcpServerActions();

  const specs = data?.specifications ?? [];
  const selection = useMemo(() => resolveSelection(specs, selectionRef), [specs, selectionRef]);

  const handleDeleteServer = (server: TreeServerNode) => {
    const toolLabel = server.tool_count === 1 ? '1 tool' : `${server.tool_count} tools`;
    if (!confirm(`Delete "${server.name}" and its ${toolLabel}? This cannot be undone.`)) {
      return;
    }
    actions.remove.mutate(server.id, {
      onSuccess: () => {
        if (
          selectionRef &&
          (selectionRef.type === 'server' || selectionRef.type === 'tool') &&
          selectionRef.serverId === server.id
        ) {
          setSelectionRef(null);
        }
      },
    });
  };

  const serverBusy =
    selection?.type === 'server' &&
    ((actions.start.isPending && actions.start.variables === selection.server.id) ||
      (actions.stop.isPending && actions.stop.variables === selection.server.id) ||
      (actions.remove.isPending && actions.remove.variables === selection.server.id));

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box>
          <Typography variant="h5" gutterBottom>
            MCP Servers
          </Typography>
          <Typography color="text.secondary">
            Explore specifications, servers, and tools in a hierarchical tree.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setWizardOpen(true)}>
          Generate MCP Server
        </Button>
      </Box>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {(error as Error).message}
        </Typography>
      )}

      <Paper
        variant="outlined"
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '340px 1fr' },
          minHeight: 560,
          overflow: 'hidden',
        }}
      >
        <Box sx={{ borderRight: { md: 1 }, borderColor: 'divider', bgcolor: 'background.paper' }}>
          <McpTreeNav
            specifications={specs}
            loading={isLoading}
            selection={selection}
            onSelect={(sel) => setSelectionRef(toSelectionRef(sel))}
          />
        </Box>

        <Box sx={{ p: 3, overflow: 'auto', maxHeight: 'calc(100vh - 220px)' }}>
          {selection?.type === 'server' && (
            <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
              {selection.server.status === 'running' ? (
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  startIcon={<StopIcon />}
                  disabled={serverBusy}
                  onClick={() => actions.stop.mutate(selection.server.id)}
                >
                  Stop
                </Button>
              ) : (
                <Button
                  size="small"
                  variant="outlined"
                  color="success"
                  startIcon={<PlayArrowIcon />}
                  disabled={serverBusy}
                  onClick={() => actions.start.mutate(selection.server.id)}
                >
                  Start
                </Button>
              )}
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon />}
                disabled={serverBusy}
                onClick={() => window.open(mcpServersApi.downloadUrl(selection.server.id), '_blank')}
              >
                Download
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                disabled={serverBusy}
                onClick={() => handleDeleteServer(selection.server)}
              >
                Delete
              </Button>
            </Stack>
          )}

          {!selection && <EmptyDetailPanel />}
          {selection?.type === 'spec' && <SpecDetailPanel spec={selection.spec} />}
          {selection?.type === 'server' && (
            <ServerDetailPanel spec={selection.spec} server={selection.server} />
          )}
          {selection?.type === 'tool' && (
            <ToolDetailPanel server={selection.server} tool={selection.tool} />
          )}
        </Box>
      </Paper>

      <GenerateWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />
    </Box>
  );
}

export function SpecsPage() {
  const [viewId, setViewId] = useState<string | null>(null);
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        OpenAPI Specifications
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Upload, validate, and parse OpenAPI specs to prepare MCP tool generation.
      </Typography>
      <Stack spacing={3}>
        <SpecUploadZone />
        <SpecsTable onView={(spec) => setViewId(spec.id)} />
      </Stack>
      <SpecViewerDialog specId={viewId} onClose={() => setViewId(null)} />
    </Box>
  );
}

export function AppProviders({
  dark,
  children,
}: {
  dark: boolean;
  children: ReactNode;
}) {
  const theme = useMemo(() => (dark ? darkTheme : lightTheme), [dark]);
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export function AppShell({
  dark,
  currentPath,
  onToggleTheme,
  children,
}: {
  dark: boolean;
  currentPath: string;
  onToggleTheme: () => void;
  children: ReactNode;
}) {
  const tab = currentPath.startsWith('/mcp') ? 1 : 0;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="sticky"
        elevation={0}
        color="transparent"
        sx={{ borderBottom: 1, borderColor: 'divider', backdropFilter: 'blur(8px)' }}
      >
        <Toolbar>
          <HubIcon color="primary" sx={{ mr: 1 }} />
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 700 }}>
            OpenAPI → MCP Generator
          </Typography>
          <IconButton onClick={onToggleTheme} color="inherit">
            {dark ? <VisibilityIcon /> : <EditIcon />}
          </IconButton>
        </Toolbar>
        <Container maxWidth="xl">
          <Tabs value={tab}>{children}</Tabs>
        </Container>
      </AppBar>
    </Box>
  );
}

import DownloadIcon from '@mui/icons-material/Download';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { generateApi } from '../../api/client';
import { useGenerateMcp } from '../../hooks/useSpecs';
import type { GenerateResponse } from '../../types';

interface Props {
  selectedSpecIds: string[];
  selectedEndpoints: Record<string, Set<string>>;
  authLabels: string[];
}

export function GenerationSummary({ selectedSpecIds, selectedEndpoints, authLabels }: Props) {
  const [serverName, setServerName] = useState('Generated MCP Server');
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [runMsg, setRunMsg] = useState<string | null>(null);
  const generate = useGenerateMcp();

  const toolCount = Object.values(selectedEndpoints).reduce((n, set) => n + set.size, 0);
  const endpointList = Object.entries(selectedEndpoints).flatMap(([, set]) => Array.from(set));

  const canGenerate = selectedSpecIds.length > 0 && toolCount > 0 && !generate.isPending;

  const handleGenerate = async () => {
    setRunMsg(null);
    const payload = {
      spec_ids: selectedSpecIds,
      selected_endpoints: Object.fromEntries(
        Object.entries(selectedEndpoints).map(([id, set]) => [id, Array.from(set)]),
      ),
      server_name: serverName,
    };
    const res = await generate.mutateAsync(payload);
    setResult(res);
  };

  const handleDownload = () => {
    if (!result) return;
    window.open(generateApi.downloadUrl(result.generation_id), '_blank');
  };

  const handleRun = async () => {
    if (!result) return;
    const res = await generateApi.run(result.generation_id);
    setRunMsg(res.message ?? 'Started');
  };

  return (
    <Paper sx={{ p: 2, height: '100%', overflow: 'auto' }}>
      <Typography variant="h6" gutterBottom>
        Generated MCP Server
      </Typography>

      <TextField
        label="Server Name"
        fullWidth
        size="small"
        value={serverName}
        onChange={(e) => setServerName(e.target.value)}
        sx={{ mb: 2 }}
      />

      <Stack spacing={1} sx={{ mb: 2 }}>
        <Typography variant="body2">
          <strong>Tool Count:</strong> {toolCount}
        </Typography>
        <Typography variant="body2">
          <strong>Authentication:</strong> {authLabels.join(', ') || '—'}
        </Typography>
        <Typography variant="body2">
          <strong>Output Folder:</strong>{' '}
          {result?.output_folder ?? '(generated on server)'}
        </Typography>
      </Stack>

      <Typography variant="subtitle2" gutterBottom>
        Selected Endpoints
      </Typography>
      <List dense sx={{ maxHeight: 160, overflow: 'auto', mb: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
        {endpointList.length === 0 && (
          <ListItem>
            <ListItemText secondary="None selected" />
          </ListItem>
        )}
        {endpointList.map((ep) => (
          <ListItem key={ep} dense>
            <ListItemText
              primary={ep}
              slotProps={{ primary: { sx: { fontSize: 12, fontFamily: 'monospace' } } }}
            />
          </ListItem>
        ))}
      </List>

      {generate.isPending && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption">Generating…</Typography>
          <LinearProgress />
        </Box>
      )}

      {generate.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(generate.error as Error).message}
        </Alert>
      )}

      {result && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Generated {result.tool_count} tools — {result.files.length} files
        </Alert>
      )}

      {result?.logs?.length ? (
        <Box
          component="pre"
          sx={{
            p: 1,
            mb: 2,
            maxHeight: 120,
            overflow: 'auto',
            fontSize: 11,
            bgcolor: 'action.hover',
            borderRadius: 1,
          }}
        >
          {result.logs.join('\n')}
        </Box>
      ) : null}

      {result?.files?.length ? (
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2">Folder Preview</Typography>
          <Box sx={{ fontFamily: 'monospace', fontSize: 12 }}>
            {result.files.map((f) => (
              <div key={f}>{f}</div>
            ))}
          </Box>
        </Box>
      ) : null}

      {runMsg && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {runMsg}
        </Alert>
      )}

      <Stack spacing={1}>
        <Button
          variant="contained"
          fullWidth
          disabled={!canGenerate}
          onClick={() => void handleGenerate()}
          startIcon={generate.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          Generate
        </Button>
        <Button
          variant="outlined"
          fullWidth
          startIcon={<DownloadIcon />}
          disabled={!result}
          onClick={handleDownload}
        >
          Download ZIP
        </Button>
        <Button
          variant="outlined"
          color="secondary"
          fullWidth
          startIcon={<PlayArrowIcon />}
          disabled={!result}
          onClick={() => void handleRun()}
        >
          Run
        </Button>
      </Stack>
    </Paper>
  );
}

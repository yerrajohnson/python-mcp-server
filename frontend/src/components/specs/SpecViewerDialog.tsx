import CloseIcon from '@mui/icons-material/Close';
import {
  Box,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useSpecification } from '../../hooks/useSpecs';
import { specsApi } from '../../api/client';
import { useQuery } from '@tanstack/react-query';

interface Props {
  specId: string | null;
  onClose: () => void;
}

export function SpecViewerDialog({ specId, onClose }: Props) {
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
            {spec.error_message && (
              <Typography color="error">{spec.error_message}</Typography>
            )}
            <Box>
              <Typography gutterBottom sx={{ fontWeight: 600 }}>
                Auth
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 1 }}>
                {(spec.parsed?.auth_schemes ?? []).map((a) => (
                  <Chip key={a.name} label={`${a.name} (${a.type})`} size="small" />
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
                <Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>
                  {ep.path}
                </Typography>
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

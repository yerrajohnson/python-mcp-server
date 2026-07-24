import {
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  Paper,
  TextField,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { specsApi } from '../../api/client';
import { endpointKey, type EndpointInfo, type Specification } from '../../types';

interface Props {
  selectedSpecIds: string[];
  selectedEndpoints: Record<string, Set<string>>;
  onToggleEndpoint: (specId: string, key: string) => void;
  onSelectAll: (specId: string, keys: string[], select: boolean) => void;
}

export function EndpointPanel({
  selectedSpecIds,
  selectedEndpoints,
  onToggleEndpoint,
  onSelectAll,
}: Props) {
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  const queries = useQueries({
    queries: selectedSpecIds.map((id) => ({
      queryKey: ['specification', id],
      queryFn: () => specsApi.get(id),
    })),
  });

  const specs = queries
    .map((q) => q.data)
    .filter((s): s is Specification => Boolean(s?.parsed));

  const loading = queries.some((q) => q.isLoading);

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    specs.forEach((s) => s.parsed?.tags.forEach((t) => tags.add(t)));
    return Array.from(tags).sort();
  }, [specs]);

  if (!selectedSpecIds.length) {
    return (
      <Paper sx={{ p: 3, height: '100%' }}>
        <Typography color="text.secondary">Select a specification to configure tools.</Typography>
      </Paper>
    );
  }

  if (loading) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center', height: '100%' }}>
        <CircularProgress />
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 2, height: '100%', overflow: 'auto' }}>
      <Typography variant="h6" gutterBottom>
        Authentication & Endpoints
      </Typography>

      {specs.map((spec) => {
        const auth = spec.parsed!.auth_schemes;
        const endpoints = spec.parsed!.endpoints;
        const selected = selectedEndpoints[spec.id] ?? new Set<string>();

        const filtered = endpoints.filter((ep) => {
          const q = search.toLowerCase();
          const matchesSearch =
            !q ||
            ep.path.toLowerCase().includes(q) ||
            (ep.summary ?? '').toLowerCase().includes(q) ||
            (ep.tool_name ?? '').toLowerCase().includes(q);
          const matchesTag = !tagFilter || ep.tags.includes(tagFilter);
          return matchesSearch && matchesTag;
        });

        const byTag = groupByTag(filtered);
        const allKeys = filtered.map(endpointKey);

        return (
          <Box key={spec.id} sx={{ mb: 3 }}>
            <Typography gutterBottom sx={{ fontWeight: 700 }}>
              {spec.parsed!.info.title}
            </Typography>

            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Authentication
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 1, mb: 2 }}>
              {auth.map((a) => (
                <Chip
                  key={a.name}
                  label={labelAuth(a.type)}
                  color={a.type === 'none' ? 'default' : 'secondary'}
                  size="small"
                />
              ))}
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 1, mb: 1 }}>
              <TextField
                size="small"
                placeholder="Search endpoints…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                sx={{ minWidth: 200, flex: 1 }}
              />
              <Button size="small" onClick={() => onSelectAll(spec.id, allKeys, true)}>
                Select all
              </Button>
              <Button size="small" onClick={() => onSelectAll(spec.id, allKeys, false)}>
                Deselect all
              </Button>
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 0.5, mb: 2 }}>
              <Chip
                label="All tags"
                size="small"
                variant={tagFilter === null ? 'filled' : 'outlined'}
                onClick={() => setTagFilter(null)}
              />
              {allTags.map((t) => (
                <Chip
                  key={t}
                  label={t}
                  size="small"
                  variant={tagFilter === t ? 'filled' : 'outlined'}
                  onClick={() => setTagFilter(t)}
                />
              ))}
            </Box>

            <Divider sx={{ mb: 1 }} />

            {Object.entries(byTag).map(([tag, eps]) => (
              <Box key={tag} sx={{ mb: 1.5 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  {tag}
                </Typography>
                {eps.map((ep) => {
                  const key = endpointKey(ep);
                  return (
                    <FormControlLabel
                      key={key}
                      control={
                        <Checkbox
                          size="small"
                          checked={selected.has(key)}
                          onChange={() => onToggleEndpoint(spec.id, key)}
                        />
                      }
                      label={
                        <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 1 }}>
                          <Chip label={ep.method} size="small" sx={{ minWidth: 56 }} />
                          <Typography variant="body2">
                            {ep.summary || ep.tool_name || ep.path}
                          </Typography>
                        </Box>
                      }
                      sx={{ display: 'flex', ml: 0 }}
                    />
                  );
                })}
              </Box>
            ))}
          </Box>
        );
      })}
    </Paper>
  );
}

function groupByTag(endpoints: EndpointInfo[]): Record<string, EndpointInfo[]> {
  const map: Record<string, EndpointInfo[]> = {};
  for (const ep of endpoints) {
    const tag = ep.tags[0] || 'default';
    (map[tag] ??= []).push(ep);
  }
  return map;
}

function labelAuth(type: string): string {
  switch (type) {
    case 'apiKey':
      return 'API Key';
    case 'bearer':
      return 'Bearer Token';
    case 'oauth2':
      return 'OAuth2';
    case 'basic':
      return 'Basic Auth';
    default:
      return 'No Authentication';
  }
}
